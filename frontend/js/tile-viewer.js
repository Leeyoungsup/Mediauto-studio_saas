/**
 * WSI Tile Viewer — Canvas text text text text
 * PyQt5 wsi_view_widget.py + wsi_tile_manager.py text JStext text
 *
 * text: WSI level-0 text text (scene text)
 * text: text zoomtext text OpenSlide leveltext text text text canvastext text
 *
 * text text (PyQt5 text text):
 *  - text text text text text text text text text (fallback)
 *  - text text text text text text → text text text
 */

import { api } from './api.js?v=20260526-01';

const TILE_SIZE = 1024;
const VIEWER_FAST_THUMBNAIL_SIZE = 300;
// text text text text — text HTTP/1.1 per-origin text(6)text text.
// text text text text text text text text abort text text text,
// text/text text text text text text text _activeLoads text text text
// text text text text stall text text.
const MAX_CONCURRENT_LOADS = 6;

// 3text stage text — text backend slide_manager.STAGE_DOWNSAMPLES text text
//   stage 0: level0 1024x1024 text   (downsample 1)
//   stage 1: level0 4096x4096 → 1024   (downsample 4)
//   stage 2: level0 8192x8192 → 1024   (downsample 8)
const STAGE_DOWNSAMPLES = [1, 4, 8];

/**
 * text text text — text SpatialGridtext text
 * text grid_size text text text text text text O(1)text text
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

        // text text
        this.slideId = null;
        this.slideInfo = null;

        // text text (scene text = level-0 px)
        this.viewCenterX = 0;
        this.viewCenterY = 0;
        this.zoom = 1.0;
        this.minZoom = 0.001;
        this.maxZoom = 40.0;
        this.fitBounds = null;

        // text text — text text text text (fallbacktext). NDP text text text text.
        this._tileCache = new Map();  // "level/tx/ty" -> HTMLImageElement
        this._tileLoading = new Set();
        // text text — key → fade start timestamp (ms). text text current-level
        // child text alpha 0 → 1 text text OSD text text text text text text.
        this._tileFadeStart = new Map();
        this._fadeDurationMs = 250;
        this._thumbnailBitmap = null;  // text text text text (slide text text 1text text)
        // ── NDP text toggle (Hamamatsu text) ──
        // app.js text setColorCorrectionEnabled() text text. text OFF.
        // ON text text/text URL text ?ndp=true text /ndp/ text text — text
        // ndpmatch text JPEG text text text text text. text CPU text text.
        this._colorCorrectionEnabled = false;
        this._maxCacheTiles = 3000;
        this._loadQueue = [];         // text text text
        this._loadQueuedKeys = new Set();
        this._activeLoads = 0;
        // text Image text — text text text abort text
        this._inflightImages = new Set();
        // text generation — onload text text generation text text stale text
        this._loadGeneration = 0;

        // 3-stage text text — text text text 3text stage level text text text text
        // text text text text text.
        this._preloadKeys = null;   // Set<string> of tile keys that belong to initial preload
        this._preloadTotal = 0;
        this._preloadDone = 0;
        this._isPreloading = false;

        // text text
        this._isPanning = false;
        this._lastPanX = 0;
        this._lastPanY = 0;

        // text text
        this.detectionCells = [];
        this.hiddenDetectionCells = [];
        this.canEditDetectionResults = true;
        this.classVisibility = {};   // {class_id: bool}
        this.classColorOverride = null;  // {class_id: '#hex'} — set per AI task to override CLASS_COLORS
        this.classConfidence = {};   // {class_id: float} text threshold (text defaultConfidence)
        this.defaultConfidence = 0.01;  // text text text text text (PD-L1/HER2 text 0.1)
        this._spatialGrid = null;    // SpatialGrid for O(1) viewport query
        this._hiddenSpatialGrid = null;
        this._highlightedCellIdx = -1; // Alt+Click text text text
        this._highlightedCellIdxSet = null; // Alt+Drag text text text Set
        this._highlightedHiddenCellIdxSet = null;
        this.onCellEditRequested = null; // (idx, cell, screenX, screenY) callback
        this.onCellsMultiEditRequested = null; // (indices, cells, screenX, screenY) callback
        this.onHiddenCellsMultiEditRequested = null; // (indices, hidden cells, screenX, screenY) callback
        this.onCellAddRequested = null;  // (sx, sy, screenX, screenY) callback for Alt+right-click
        this.onCellEdited = null;        // text text text
        this.onPatchCellEditRequested = null;
        this.onPatchCellsMultiEditRequested = null;
        // Alt+Drag text text
        this._altPending = null;   // { sx, sy, cx, cy, clientX, clientY }
        this._lassoActive = false;
        this._lassoPoints = [];    // [[sx, sy], ...] scene text
        // Undo/Redo (text text)
        this._undoStack = [];
        this._redoStack = [];
        this._maxUndo = 200;
        this._annotationUndoStack = [];
        this._annotationRedoStack = [];
        this._maxAnnotationUndo = 100;

        // Segmentation text
        this._segOverlay = null;     // {image, sceneX, sceneY, sceneW, sceneH}
        this.segClassVisibility = {}; // {cls_id: bool}

        // Virtual Stain (VS IHC) text — text text text
        // meta: {slideId, stainType, targetMpp, originX, originY, sceneW, sceneH,
        //        tileSize, levels: [{level,width,height,nx,ny}...], roiPolygons}
        this._vsOverlay = null;
        this._vsVisible = true;
        this._vsSplitMode = false;   // true: text text text VS text (text: text IHC)
        this._vsSplitFrac = 0.5;     // text text (0..1, text text text)
        this._vsSplitDragging = false;
        this._vsSplitHandleW = 10;   // text hit-area (±px)

        // VS text text (level/tx/ty text)
        this._vsTileCache = new Map();    // key → HTMLImageElement (LRU: Map insertion order)
        this._vsTileLoading = new Set();  // in-flight keys
        this._vsTileMissing = new Set();  // 404 text (text text text text)
        this._vsLoadQueue = [];           // VS text text text
        this._vsActiveLoads = 0;          // text text text VS text text text
        this._vsMaxTiles = 512;

        // ── Annotation ──
        this.annotations = [];        // [{id, name, type, coordinates, color, visible, selected, group}]
        this.cellAnnotationDisplayMode = 'bbox';
        this.drawMode = null;         // 'polygon' | 'brush' | 'rectangle' | 'point' | 'cut' | 'rect-1mm2' | 'circle-1mm2' | 'ruler' | null
        this._drawingPoints = [];     // text text text text (scene)
        this._drawingStart = null;    // text text (scene)
        this._drawingCurrent = null;  // text/text text text (scene)
        this._brushSizePx = Number(localStorage.getItem('annotationBrushSizePx') || 28);
        this._brushSizePx = Math.max(4, Math.min(120, this._brushSizePx));
        this.annotationStrokeWidth = 2;
        this.annotationFillOpacity = 0.1;
        this.annotationDrawColor = [0, 255, 0];
        this.hiddenAnnotationClassIds = new Set();
        // Ruler — text text. annotation text text text text text.
        // mode text / text text text text text.
        this._rulerStart = null;      // [sx, sy]
        this._rulerEnd = null;        // [sx, sy] — text text text text text text text
        this._rulerFinalized = false; // true text text text text text text text text
        this._isDrawing = false;
        this._annotationCounter = 0;
        this.selectedAnnotationId = null;
        this._insertVertexPreview = null; // {annId, insertIndex, point:[sx,sy]} Ctrl+polygon edge insert preview
        this._mergeHover = null;       // {annIds:[id,id], scenePoint:[sx,sy]} same-class polygon merge affordance
        this._dragControlPoint = null;  // {annId, pointIndex} text text text
        this._dragAnnotation = null;    // {annId, startScene} text text text
        this._lastDrawDragScene = null; // text text text text

        // text
        this.onZoomChange = null;
        this.onViewChange = null;
        this.onPreloadStart = null;     // () => {}  3-stage text text
        this.onPreloadProgress = null;  // (done, total) => {}
        this.onPreloadComplete = null;  // () => {}  3-stage text text
        this.onAnnotationCreated = null;   // (annotation) => {}
        this.onAnnotationSelected = null;  // (annotation|null) => {}
        this.onAnnotationDeleted = null;   // (annotation) => {}
        this.onAnnotationChanged = null;   // (annotation) => {}
        this.onAnnotationContextMenu = null; // (annotation, event) => {}
        this.onDrawModeChange = null;      // (mode) => {}
        this.extraOverlayLayers = [];

        // text text text
        this._renderPending = false;

        this._setupEvents();
        this._resizeCanvas();
        window.addEventListener('resize', () => this._resizeCanvas());
    }

    addOverlayLayer(layer) {
        if (!layer || typeof layer.draw !== 'function') return;
        if (!this.extraOverlayLayers.includes(layer)) {
            this.extraOverlayLayers.push(layer);
            this.requestRender();
        }
    }

    removeOverlayLayer(layer) {
        const idx = this.extraOverlayLayers.indexOf(layer);
        if (idx >= 0) {
            this.extraOverlayLayers.splice(idx, 1);
            this.requestRender();
        }
    }

    clearOverlayLayers() {
        this.extraOverlayLayers = [];
        this.requestRender();
    }

    // ── text text ──

    loadSlide(slideId, slideInfo) {
        // text Image text abort — onload text text text cache text text text text text text
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
        this._loadQueuedKeys.clear();
        this._activeLoads = 0;
        this._thumbnailBitmap = null;
        this.detectionCells = [];
        this.annotations = [];
        this.selectedAnnotationId = null;
        this._annotationCounter = 0;
        this._annotationUndoStack = [];
        this._annotationRedoStack = [];
        this._thumbnailBitmap = null;

        // text text text text text
        this._preloadKeys = null;
        this._preloadTotal = 0;
        this._preloadDone = 0;
        this._isPreloading = false;

        const str_preload_slide_id = this.slideId;
        this._loadThumbnailFallbackImmediate().finally(() => {
            if (this.slideId !== str_preload_slide_id) return;
            this._preloadAllStageLevels();
        });
        this.fitToWindow();
        // 3 stage level text text — text text text text
        // Overview preload starts after the thumbnail gets first chance to paint.
        // text text text text 1text text — text/text text miss text text text text text
    }

    async _loadThumbnailFallback() {
        if (!this.slideId) return;
        const str_slide_id = this.slideId;
        const int_gen = this._loadGeneration;
        await api.ensureMediaReady();
        if (this.slideId !== str_slide_id) return;

        // ndpMatch text URL text text — text ndpmatch text text
        const bool_auto_ndp = api.shouldUseNdpMatch?.(this.slideInfo) || false;
        const bool_ndp = !!this._colorCorrectionEnabled || bool_auto_ndp;

        // 0text — text text text text DOM <img> text (text 0ms).
        // Use only the fast matched thumbnail for viewer startup.
        const img_small = new Image();
        this._inflightImages.add(img_small);
        img_small.onload = () => {
            this._inflightImages.delete(img_small);
            if (int_gen !== this._loadGeneration) return;
            if (this.slideId !== str_slide_id) return;
            this._thumbnailBitmap = img_small;
            this.requestRender();
        };
        img_small.onerror = (e) => {
            this._inflightImages.delete(img_small);
            if (int_gen !== this._loadGeneration) return;
            console.warn('[tile-viewer] small thumb load failed', img_small.src, e);
        };
        const str_small_url = api.thumbnailUrl(str_slide_id, VIEWER_FAST_THUMBNAIL_SIZE, bool_ndp, this.slideInfo);
        if (str_small_url) img_small.src = str_small_url;


    }

    _loadThumbnailFallbackImmediate() {
        if (!this.slideId) return Promise.resolve(false);
        const str_slide_id = this.slideId;
        const int_gen = this._loadGeneration;
        const bool_auto_ndp = api.shouldUseNdpMatch?.(this.slideInfo) || false;
        const bool_ndp = !!this._colorCorrectionEnabled || bool_auto_ndp;
        return new Promise((resolve) => {
            let bool_done = false;
            const finish = (ok = false) => {
                if (bool_done) return;
                bool_done = true;
                resolve(ok);
            };
            // Start tile preload after the fast matched thumbnail gets a chance to paint.
            setTimeout(() => finish(false), 1500);

            const el_sidebar_thumb = document.querySelector(
                `.slide-list-item[data-slide-id="${str_slide_id}"] .slide-thumb`
            );
            const paintSidebarThumb = () => {
                if (bool_ndp && !String(el_sidebar_thumb?.currentSrc || el_sidebar_thumb?.src || '').includes('ndp=true')) return;
                if (int_gen !== this._loadGeneration) return;
                if (this.slideId !== str_slide_id) return;
                if (!el_sidebar_thumb || el_sidebar_thumb.naturalWidth <= 0) return;
                this._thumbnailBitmap = el_sidebar_thumb;
                this.requestRender();
            };
            if (el_sidebar_thumb?.complete) {
                paintSidebarThumb();
            } else if (el_sidebar_thumb) {
                el_sidebar_thumb.addEventListener('load', paintSidebarThumb, { once: true });
            }

            api.ensureMediaReady().then(() => {
                if (this.slideId !== str_slide_id) return finish(false);

                const loadImage = (url, label, applyImage, onError, resolveOnLoad = false) => {
                    if (!url) return false;
                    const img = new Image();
                    this._inflightImages.add(img);
                    img.onload = () => {
                        this._inflightImages.delete(img);
                        if (int_gen !== this._loadGeneration) return;
                        if (this.slideId !== str_slide_id) return;
                        applyImage(img);
                        this.requestRender();
                        if (resolveOnLoad) finish(true);
                    };
                    img.onerror = (e) => {
                        this._inflightImages.delete(img);
                        if (int_gen !== this._loadGeneration) return;
                        console.warn(`[tile-viewer] ${label} load failed`, img.src, e);
                        if (typeof onError === 'function') onError();
                    };
                    img.src = url;
                    return true;
                };

                const applyThumb = (img) => { this._thumbnailBitmap = img; };

                const str_match_thumb_url = api.thumbnailUrl(str_slide_id, VIEWER_FAST_THUMBNAIL_SIZE, bool_ndp, this.slideInfo);

                let bool_started = false;
                bool_started = loadImage(str_match_thumb_url, 'thumbnail', applyThumb, null, true) || bool_started;
                if (!bool_started) finish(false);
            }).catch(() => finish(false));
        });
    }

    _preloadAllStageLevels() {
        if (!this.slideInfo) return;
        // text stage 2 (text text) text text text.
        // stage 0, 1 text text zoom in text text on-demand text text.
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
            this._queueTileTask(t);
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
        const bounds = this.fitBounds;
        const [slideW, slideH] = this.slideInfo.dimensions;
        const imgW = bounds ? Number(bounds.w || 0) : slideW;
        const imgH = bounds ? Number(bounds.h || 0) : slideH;
        if (imgW <= 0 || imgH <= 0) return;
        const vw = this._viewW;
        const vh = this._viewH;
        this.zoom = Math.min(vw / imgW, vh / imgH);
        if (!bounds) this.minZoom = this.zoom;
        this.viewCenterX = bounds ? Number(bounds.x || 0) + imgW / 2 : imgW / 2;
        this.viewCenterY = bounds ? Number(bounds.y || 0) + imgH / 2 : imgH / 2;

        const baseMag = (0.25 / this.slideInfo.mpp) * 40.0;
        this.maxZoom = 80.0 / baseMag;

        this._clampView();
        this._emitZoomChange();
        this.requestRender();
    }

    // ── text text ──

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
        // stage index text (0/1/2). level text text stage text text text.
        if (effectiveMpp < 2.0) return 0;
        if (effectiveMpp < 15.0) return 1;
        return 2;
    }

    _getLevelStages() {
        // 3text stage text text [0, 1, 2] — stage index text text level text text
        return [0, 1, 2];
    }

    _stageDownsample(stage) {
        return STAGE_DOWNSAMPLES[stage];
    }

    _stageDimensions(stage) {
        // backend text stage_dimensions text text text, text level 0 text text
        if (this.slideInfo &&
            Array.isArray(this.slideInfo.stage_dimensions) &&
            this.slideInfo.stage_dimensions[stage]) {
            return this.slideInfo.stage_dimensions[stage];
        }
        const [w0, h0] = this.slideInfo.dimensions;
        const ds = STAGE_DOWNSAMPLES[stage];
        return [Math.max(1, Math.ceil(w0 / ds)), Math.max(1, Math.ceil(h0 / ds))];
    }

    // ── text ──

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

    setViewBounds(bounds = null) {
        if (!bounds) {
            this.fitBounds = null;
        } else {
            const x = Number(bounds.x || 0);
            const y = Number(bounds.y || 0);
            const w = Number(bounds.w || 0);
            const h = Number(bounds.h || 0);
            this.fitBounds = w > 0 && h > 0 ? { x, y, w, h } : null;
        }
        this.requestRender();
        if (this.onViewChange) this.onViewChange();
    }

    _emitZoomChange() {
        if (this.onZoomChange) {
            this.onZoomChange(this.zoom, this.getMagnification(), this.getEffectiveMpp());
        }
        if (this.onViewChange) {
            this.onViewChange();
        }
    }

    // ── text ──

    _setupEvents() {
        // ── text ──
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

        let suppressContextMenuUntil = 0;
        const suppressAltContextMenu = (e) => {
            const recentlyUsedAltRight = Date.now() < suppressContextMenuUntil;
            if (!e.altKey && !recentlyUsedAltRight) return;
            const viewerRoot = this.canvas.closest('#viewer-container');
            const target = e.target;
            const isViewerContext = target === this.canvas ||
                target === this.overlayCanvas ||
                (viewerRoot && viewerRoot.contains(target)) ||
                this._altPending ||
                this._lassoActive ||
                recentlyUsedAltRight;
            if (!isViewerContext) return;
            e.preventDefault();
            e.stopPropagation();
            if (typeof e.stopImmediatePropagation === 'function') {
                e.stopImmediatePropagation();
            }
        };
        window.addEventListener('contextmenu', suppressAltContextMenu, true);
        this.canvas.addEventListener('contextmenu', suppressAltContextMenu, true);
        if (this.overlayCanvas) {
            this.overlayCanvas.addEventListener('contextmenu', suppressAltContextMenu, true);
        }

        // ── text ──
        this.canvas.addEventListener('mousedown', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;
            const [sx, sy] = this.canvasToScene(cx, cy);

            // VS Split mode: text text hit-test (text)
            if (e.button === 0 && this._vsSplitMode && this._vsOverlay && this._vsVisible) {
                const splitX = this._viewW * this._vsSplitFrac;
                if (Math.abs(cx - splitX) <= this._vsSplitHandleW) {
                    this._vsSplitDragging = true;
                    this.canvas.style.cursor = 'ew-resize';
                    e.preventDefault();
                    return;
                }
            }

            // Alt + text/text: text text (text=text, text=text text text)
            // mousedown text text text — mousemovetext text text text
            if (this.canEditDetectionResults && e.altKey && e.button === 2 && !this.drawMode) {
                suppressContextMenuUntil = Date.now() + 2000;
                this._altPending = {
                    sx, sy, cx, cy,
                    clientX: e.clientX, clientY: e.clientY,
                    hiddenOther: true,
                    rightButton: true,
                };
                this._lassoActive = false;
                this._lassoPoints = [];
                e.preventDefault();
                e.stopPropagation();
                return;
            }

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

            if (e.button === 0 && e.altKey && !this.drawMode && !this.cellAnnotationPatchViewActive) {
                const insertHit = this._findPolygonEdgeInsertTarget(sx, sy);
                if (insertHit) {
                    this._insertVertexAtEdge(insertHit);
                    e.preventDefault();
                    return;
                }
            }

            if (this.canEditDetectionResults && e.altKey && e.button === 0 &&
                    (this.detectionCells.length > 0 || this._cellAnnotationEditModeActive())) {
                this._altPending = {
                    sx, sy, cx, cy,
                    clientX: e.clientX, clientY: e.clientY,
                    patchAnnotations: !this.detectionCells.length && this._cellAnnotationEditModeActive(),
                };
                this._lassoActive = false;
                this._lassoPoints = [];
                e.preventDefault();
                return;
            }

            // Shift + text: text text text (drawMode text text text — drawMode text text click text).
            // detection text text text text — class_names text text text text text text.
            // text text Shift+A text text text (Ctrl text text text — Ctrl text text modifier).
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

            // text text
            if (this.drawMode && e.button === 0 && !e.ctrlKey) {
                this._onDrawMouseDown(sx, sy, cx, cy, e);
                return;
            }

            // text text text (text annotationtext text)
            // Ctrl text text annotation text pan text (text text text)
            if (e.button === 0 && !this.drawMode && !e.ctrlKey) {
                const cp = this._hitControlPoint(cx, cy);
                if (cp) {
                    this.pushAnnotationUndo();
                    this._dragControlPoint = cp;
                    this.canvas.style.cursor = 'move';
                    return;
                }

                // annotation text text / text
                const hitAnn = this._hitAnnotation(sx, sy);
                if (hitAnn) {
                    this.selectAnnotation(hitAnn.id);
                    this.canvas.style.cursor = 'grabbing';
                }

                // text text text → text text
                if (!hitAnn && !e.ctrlKey && this.selectedAnnotationId) {
                    this.selectAnnotation(null);
                }
            }

            // Ctrl+text text text text
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

            if (e.altKey && !this._isPanning && !this._dragControlPoint && !this._dragAnnotation &&
                    !this._vsSplitDragging) {
                this.canvas.style.cursor = 'crosshair';
            }

            // Alt+text text text
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

            // VS Split text text
            if (this._vsSplitDragging) {
                const w = this._viewW;
                let frac = cx / w;
                // text text text (text 5%)
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
            if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation && !this.drawMode && !this.cellAnnotationPatchViewActive) {
                this._setInsertVertexPreview(e.altKey ? this._findPolygonEdgeInsertTarget(sx, sy) : null);
                if (this._insertVertexPreview) {
                    this.canvas.style.cursor = 'copy';
                    return;
                }
            }
            // hover text cursor text (text/text/text text text text)
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

            // text text
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

            // annotation text text
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

            // text text
            if (this.drawMode && this._isDrawing) {
                this._onDrawMouseMove(sx, sy, cx, cy);
                return;
            }
            // 1mm² text text text text text text text text text
            if (this.drawMode === 'brush') {
                this._drawingCurrent = [sx, sy];
                this.requestRender();
            }
            if (this.drawMode === 'rect-1mm2' || this.drawMode === 'circle-1mm2') {
                this._drawingCurrent = [sx, sy];
                this.requestRender();
            }
            // Ruler — text text text text text text (text text text).
            // text/text ±2° text preview text text text text text text text.
            if (this.drawMode === 'ruler' && this._rulerStart && !this._rulerFinalized) {
                this._rulerEnd = this._snapRulerEnd(
                    this._rulerStart[0], this._rulerStart[1], sx, sy);
                this.requestRender();
            }

            // text
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
            // Alt+text/text text text
            if (this._altPending) {
                const pending = this._altPending;
                this._altPending = null;
                if (this._lassoActive) {
                    this._lassoActive = false;
                    const pts = this._lassoPoints;
                    this._lassoPoints = [];
                    if (pts.length >= 3) {
                        const list_indices = pending.patchAnnotations
                            ? this._findCellAnnotationsInPolygon(pts)
                            : pending.hiddenOther
                            ? this._findHiddenCellsInPolygon(pts)
                            : this._findCellsInPolygon(pts);
                        if (list_indices.length > 0) {
                            // text text text text closetext highlighttext text
                            // text text text text text highlight Settext text
                            if (pending.patchAnnotations) {
                                if (this.onPatchCellsMultiEditRequested) {
                                    const list_cells = list_indices.map(i => this.annotations[i]);
                                    this.onPatchCellsMultiEditRequested(list_indices, list_cells, e.clientX, e.clientY);
                                }
                            } else if (pending.hiddenOther) {
                                if (this.onHiddenCellsMultiEditRequested) {
                                    const list_cells = list_indices.map(i => this.hiddenDetectionCells[i]);
                                    this.onHiddenCellsMultiEditRequested(list_indices, list_cells, e.clientX, e.clientY);
                                }
                            } else if (this.onCellsMultiEditRequested) {
                                const list_cells = list_indices.map(i => this.detectionCells[i]);
                                this.onCellsMultiEditRequested(list_indices, list_cells, e.clientX, e.clientY);
                            }
                            this._highlightedCellIdx = -1;
                            if (pending.hiddenOther) {
                                this._highlightedCellIdxSet = null;
                                this._highlightedHiddenCellIdxSet = new Set(list_indices);
                            } else {
                                this._highlightedHiddenCellIdxSet = null;
                                this._highlightedCellIdxSet = new Set(list_indices);
                            }
                        }
                    }
                    this.requestRender();
                } else {
                    if (pending.rightButton) {
                        if (this.onCellAddRequested) {
                            this.onCellAddRequested(pending.sx, pending.sy, pending.clientX, pending.clientY);
                        }
                        this.requestRender();
                        return;
                    }
                    // text Alt+text: text text text text
                    const hit = pending.patchAnnotations
                        ? this._findNearestCellAnnotation(pending.sx, pending.sy, 30)
                        : this._findNearestCell(pending.sx, pending.sy, 30);
                    if (hit) {
                        if (pending.patchAnnotations && this.onPatchCellEditRequested) {
                            this.onPatchCellEditRequested(hit.index, hit.cell, pending.clientX, pending.clientY);
                        } else if (this.onCellEditRequested) {
                            this.onCellEditRequested(hit.index, hit.cell, pending.clientX, pending.clientY);
                        }
                        this._highlightedCellIdxSet = null;
                        this._highlightedCellIdx = pending.patchAnnotations ? -1 : hit.index;
                        this.requestRender();
                    }
                }
                return;
            }

            // Shift+click text — text text text text text text (text text).
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

        // ── text: text text text + text text text ──
        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            suppressContextMenuUntil = Date.now() + 500;
            if (e.altKey) return;
            if (this.drawMode) {
                this.setDrawMode(null);
                return;
            }
            const rect = this.canvas.getBoundingClientRect();
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;
            const [sx, sy] = this.canvasToScene(cx, cy);
            const ann = this._hitAnnotation(sx, sy);
            if (ann) {
                this.selectAnnotation(ann.id);
                if (this.onAnnotationContextMenu) this.onAnnotationContextMenu(ann, e);
            }
        });

        // ── text: annotation text ──
        this.canvas.addEventListener('dblclick', (e) => {
            if (!this.drawMode) {
                const rect = this.canvas.getBoundingClientRect();
                const [sx, sy] = this.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
                const hitAnn = this._hitAnnotation(sx, sy);
                if (hitAnn) this.centerOnAnnotation(hitAnn);
            }
        });

        // ── text ──
        window.addEventListener('keydown', (e) => {
            if ((e.key === 'Control' || e.key === 'Alt') &&
                    !this._isPanning && !this._dragControlPoint && !this._dragAnnotation &&
                    !this._vsSplitDragging) {
                this.canvas.style.cursor = e.key === 'Alt' ? 'crosshair' : 'pointer';
                if (e.key === 'Alt') document.body.classList.add('viewer-alt-held');
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
                    this.setDrawMode(null); // text text
                }
            }
            if (e.key === 'Delete' && this.selectedAnnotationId) {
                this.deleteAnnotation(this.selectedAnnotationId);
            }
            // Shift text text text text — text text text text text text text.
            // (drawMode/text text text text text text, text detectionCells text text text.)
        });
        window.addEventListener('keyup', (e) => {
            if (e.key === 'Alt') {
                document.body.classList.remove('viewer-alt-held');
                this._setInsertVertexPreview(null);
            }
            if (e.key === 'Control') {
                this._setMergeHover(null);
            }
            if (e.key === 'Control' || e.key === 'Alt' || e.key === 'Shift') {
                // text cursor text (drawMode/text/text) text text grab text text.
                if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation &&
                        !this._vsSplitDragging) {
                    this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
                }
            }
        });
        // text text text text Shift text text keyup text text text text text blur text text.
        window.addEventListener('blur', () => {
            document.body.classList.remove('viewer-alt-held');
            this._setInsertVertexPreview(null);
            if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation &&
                    !this._vsSplitDragging) {
                this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
            }
        });

        // ── text ──
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
        // text text text text — text text text 1:1 text text
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

    // ── text ──

    requestRender() {
        if (this._renderPending) return;
        this._renderPending = true;
        requestAnimationFrame(() => {
            this._renderPending = false;
            this._render();
        });
    }

    /**
     * child scene text **text text fallback text** text text text text text.
     * child text parent text text text parent text text 2x2 = 4 text text.
     * text parent text child text text text text text clamp text.
     *
     * text: **text level text** text (text stage text), text level text child text
     * text parent text text. text cache text text text level text text.
     * (text text text text level text text text text text text level text text)
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
            // child text text parent text text text (text ~ text)
            const int_ptx_min = Math.floor(sceneX / tileScene);
            const int_pty_min = Math.floor(sceneY / tileScene);
            // child text text (1e-6) text text text text text text text text text text
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
        // text draw text identity transform text device pixel text text
        // (text scale+drawImage text rounding text text text).
        // VS overlay text text CSS text text text dpr transform text text text text.
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        if (!this.slideInfo) {
            this.ctx.fillStyle = '#fff';
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            return;
        }

        const ctx = this.ctx;
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        ctx.imageSmoothingEnabled = false;

        const effectiveMpp = this.getEffectiveMpp();
        const level = this._getStageLevel(effectiveMpp);
        const downsample = this._stageDownsample(level);
        const [levelW, levelH] = this._stageDimensions(level);

        // text text (scene text)
        const halfVW = this._viewW / this.zoom / 2;
        const halfVH = this._viewH / this.zoom / 2;
        const viewLeft = this.viewCenterX - halfVW;
        const viewTop = this.viewCenterY - halfVH;
        const viewRight = this.viewCenterX + halfVW;
        const viewBottom = this.viewCenterY + halfVH;

        // text text
        const tileSceneSize = TILE_SIZE * downsample;
        const txMin = Math.max(0, Math.floor(viewLeft / tileSceneSize));
        const tyMin = Math.max(0, Math.floor(viewTop / tileSceneSize));
        const txMax = Math.min(Math.ceil(levelW / TILE_SIZE) - 1, Math.ceil(viewRight / tileSceneSize));
        const tyMax = Math.min(Math.ceil(levelH / TILE_SIZE) - 1, Math.ceil(viewBottom / tileSceneSize));

        // text text text (text text text text text text)
        // parent / child text — parent text strictly text text text text child text.
        // FIFO + MAX_CONCURRENT_LOADS text parent text text text text text
        // child text text text text text.
        const list_parent_tasks = [];
        const list_child_tasks = [];
        const set_parent_enqueued = new Set();

        // text stage text "text text stage level" — fallback prefetch text
        const list_stage_unique = Array.from(new Set(this._getLevelStages())).sort((a, b) => a - b);
        const int_cur_stage_idx = list_stage_unique.indexOf(level);
        const int_parent_stage_level = (int_cur_stage_idx >= 0 && int_cur_stage_idx + 1 < list_stage_unique.length)
            ? list_stage_unique[int_cur_stage_idx + 1]
            : -1;

        // ── Pass 1: text child text text text text text parent text text ──
        // child text parent text text text sub-pixel text text artifact text text.
        // text parent text text text text **text text** text, text/text draw text text.
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
                    // text text text text text text text→text text text text
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
                    // text child text text parent text text (text map text dedup)
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

                    // text text stage level text text text (parent text text).
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

                    // text text child text text text text — text parent text text
                    if (!this._tileLoading.has(key)) {
                        list_child_tasks.push({ level, tx, ty, key });
                    }
                }
            }
        }

        // ── device pixel text text drawImage (transform text) ──
        // CSS px text device px text snap. floor(left) + ceil(right) text text text
        // text text text text text. ceil text text floor text gap text.
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

        // ── Pass 2a: text (text text) text text text text text ──
        const bool_should_draw_thumbnail = !!this._thumbnailBitmap
            && (bool_any_missing_without_fallback || list_missing_children.length > 0);
        if (bool_should_draw_thumbnail) {
            const tb = this._thumbnailBitmap;
            const [int_scene_w, int_scene_h] = this.slideInfo.dimensions;
            const [float_thumb_x, float_thumb_y] = this.sceneToCanvas(0, 0);
            _drawAligned(tb, null, null, null, null,
                float_thumb_x, float_thumb_y,
                int_scene_w * this.zoom, int_scene_h * this.zoom);
        }

        // ── Pass 2b: fallback parent text text text text text text ──
        for (const fb of map_fallback_parents.values()) {
            const [float_px, float_py] = this.sceneToCanvas(fb.srcSceneX, fb.srcSceneY);
            _drawAligned(fb.img, 0, 0, fb.srcPixelSize, fb.srcPixelSize,
                float_px, float_py,
                fb.srcSceneSize * this.zoom, fb.srcSceneSize * this.zoom);
        }

        // ── Pass 3: text text child text (fade-in) ──
        // text text text alpha 0 → 1 text text OSD text text text text
        // text text. text parent/text text text text text text text text.
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

        // text stage text text, text text text text child text text text.
        // parent text text text text child text text text,
        // fallback text text text text.
        // child text text text text text text — text text text text text.
        const float_center_tx = (txMin + txMax) / 2;
        const float_center_ty = (tyMin + tyMax) / 2;
        list_child_tasks.sort((a, b) => {
            const float_da = (a.tx - float_center_tx) ** 2 + (a.ty - float_center_ty) ** 2;
            const float_db = (b.tx - float_center_tx) ** 2 + (b.ty - float_center_ty) ** 2;
            return float_da - float_db;
        });
        this._queueTileTasksFront([...list_parent_tasks, ...list_child_tasks]);

        // text text text text text
        this._processLoadQueue();

        // text CSS text text text — dpr transform text
        ctx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);

        // Virtual Stain text (text text text text text — text text)
        this._renderVirtualStainOverlay(ctx);

        // text text — device pixel text, dpr scale text annotation text
        this.overlayCtx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
        this.overlayCtx.clearRect(0, 0, this._viewW, this._viewH);
        // text: annotation/detection text CSS text text text.
        this._renderDetectionOverlay();
        this._renderAnnotations(this.overlayCtx);
        for (const layer of this.extraOverlayLayers || []) {
            try {
                layer.draw(this.overlayCtx, this);
            } catch (err) {
                console.error('[tile-viewer] overlay layer failed:', err);
            }
        }
    }

    _renderVirtualStainOverlay(ctx) {
        const ov = this._vsOverlay;
        if (!ov || !this._vsVisible) return;
        if (!ov.levels || ov.levels.length === 0) return;

        const canvasW = this._viewW;
        const canvasH = this._viewH;

        // text text → text text
        const [cx, cy] = this.sceneToCanvas(ov.originX, ov.originY);
        const cw = ov.sceneW * this.zoom;
        const ch = ov.sceneH * this.zoom;

        // text text
        const dx0 = Math.max(0, cx);
        const dy0 = Math.max(0, cy);
        const dx1 = Math.min(canvasW, cx + cw);
        const dy1 = Math.min(canvasH, cy + ch);
        const overlayVisible = (dx1 > dx0 && dy1 > dy0);
        if (!overlayVisible && !this._vsSplitMode) return;

        // ── text text: level width text text text text text text text text text text text text text ──
        // text text VS text(text)text text text text text text
        let chosenL = 0;
        for (let L = 0; L < ov.levels.length; L++) {
            if (ov.levels[L].width >= cw * 0.8) chosenL = L;
            else break;
        }
        const lvl = ov.levels[chosenL];
        const scaleX = ov.sceneW / lvl.width;    // scene px per level-pixel

        // text(zoom text text)text text off, text low text
        const screenPerLvlPx = this.zoom * scaleX;
        if (screenPerLvlPx > 1) {
            ctx.imageSmoothingEnabled = false;
        } else {
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = 'low';
        }

        // text scene text
        const [vsx0, vsy0] = this.canvasToScene(0, 0);
        const [vsx1, vsy1] = this.canvasToScene(canvasW, canvasH);
        const xlo = Math.max(ov.originX, vsx0);
        const ylo = Math.max(ov.originY, vsy0);
        const xhi = Math.min(ov.originX + ov.sceneW, vsx1);
        const yhi = Math.min(ov.originY + ov.sceneH, vsy1);
        if (xhi <= xlo || yhi <= ylo) {
            // text text text — split text text text (text text)
            if (!this._vsSplitMode) return;
        }

        const TS = ov.tileSize || 512;

        // text text text text draw (text/text text text text)
        // requestMissing: true text text miss text _getVsTile text text text text
        //                 false text text text text text (fallback text)
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

        // ROI text text
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

        // drawTiles: text text → text text → text text (text text) text text
        //   1) text text text(text)text text text text text text (blur pad)
        //   2) text text text (text text)
        //   3) text text text text (L-1, L-2...) text text text text text text
        //      (text text text text text text text text)
        const drawTiles = () => {
            const bgL = ov.levels.length - 1;
            if (bgL !== chosenL) {
                drawLevel(bgL, true);  // text text text → text text text
            }
            drawLevel(chosenL, true);
            for (let L = chosenL - 1; L >= 0; L--) {
                drawLevel(L, false);  // text text text text text text
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

            // text + text + text
            ctx.save();
            // text text (text)
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.moveTo(splitX, 0);
            ctx.lineTo(splitX, canvasH);
            ctx.stroke();
            // text text
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(splitX, 0);
            ctx.lineTo(splitX, canvasH);
            ctx.stroke();

            // text text text (text + text text)
            const handleY = canvasH / 2;
            const handleR = 14;
            ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(splitX, handleY, handleR, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            // text text
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
            // text text
            ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.fillRect(padX, padY, mL.width + 12, bh);
            ctx.fillStyle = '#fff';
            ctx.fillText(labelL, padX + 6, padY + 3);
            // text text
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
     * VS text text text (text text text). text text.
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
     * VS text text (LRU text + text text text text).
     * text null text text text text text text text.
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

        // text text text text text
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
                // text text overlay text text text
                if (this._vsOverlay !== task.ov) return;
                // LRU text
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
        // split modetext text overlaytext text text text
        if (this._vsSplitMode) this._vsVisible = true;
        if (!this._vsSplitMode) {
            this._vsSplitDragging = false;
            this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
        }
        this.requestRender();
    }

    // ── text text (text, text text) ──

    _tileTaskKey(task) {
        return task?.key || `${task.level}/${task.tx}/${task.ty}`;
    }

    _queueTileTask(task, front = false) {
        if (!task) return;
        const key = this._tileTaskKey(task);
        if (!key || this._tileCache.has(key) || this._tileLoading.has(key)) return;
        task.key = key;
        if (this._loadQueuedKeys.has(key)) {
            if (!front) return;
            this._loadQueue = this._loadQueue.filter(item => this._tileTaskKey(item) !== key);
            this._loadQueuedKeys.delete(key);
        }
        if (front) this._loadQueue.unshift(task);
        else this._loadQueue.push(task);
        this._loadQueuedKeys.add(key);
    }

    _queueTileTasksFront(tasks) {
        for (let i = tasks.length - 1; i >= 0; i--) {
            this._queueTileTask(tasks[i], true);
        }
    }

    _processLoadQueue() {
        while (this._loadQueue.length > 0 && this._activeLoads < MAX_CONCURRENT_LOADS) {
            const task = this._loadQueue.shift();
            this._loadQueuedKeys.delete(this._tileTaskKey(task));
            this._loadTile(task.level, task.tx, task.ty);
        }
    }

    _loadTile(level, tx, ty) {
        const key = `${level}/${tx}/${ty}`;
        if (this._tileLoading.has(key) || this._tileCache.has(key)) return;

        this._tileLoading.add(key);
        this._activeLoads++;

        // text text text text generation — text text text text text
        const int_gen = this._loadGeneration;
        const img = new Image();
        this._inflightImages.add(img);
        img.onload = () => {
            this._inflightImages.delete(img);
            this._tileLoading.delete(key);
            this._activeLoads--;
            // text text text text text text (text text text text cache text
            // text text text contamination text)
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
            // text "text" text text text text text text
            this._markPreloadTileDone(key);
            this._processLoadQueue();
        };
        img.src = api.tileUrl(this.slideId, level, tx, ty, this._colorCorrectionEnabled);
    }

    _putCache(key, img) {
        // LRU text
        if (this._tileCache.size >= this._maxCacheTiles) {
            // text text (Map text text) text text
            const oldest = this._tileCache.keys().next().value;
            this._tileCache.delete(oldest);
            this._tileFadeStart.delete(oldest);
        }
        this._tileCache.set(key, img);
    }

    /**
     * NDP text ON/OFF. Hamamatsu text text toggle text text.
     *
     * text text text text/text URL text text (text /ndp/ text text
     * JPEG text text text text) text text text text text. text text
     * text text text text text text text, text text text
     * HTTP text + text text text text text text text text text.
     */
    setColorCorrectionEnabled(bool_enabled) {
        bool_enabled = !!bool_enabled;
        if (this._colorCorrectionEnabled === bool_enabled) return;
        this._colorCorrectionEnabled = bool_enabled;
        // text URL text text text/text text text text flag text text
        this._loadGeneration++;
        for (const img of this._inflightImages) {
            try { img.onload = null; img.onerror = null; img.src = ''; } catch (e) {}
        }
        this._inflightImages.clear();
        this._tileCache.clear();
        this._tileLoading.clear();
        this._tileFadeStart.clear();
        this._loadQueue = [];
        this._loadQueuedKeys.clear();
        this._activeLoads = 0;
        this._thumbnailBitmap = null;
        this._loadThumbnailFallbackImmediate();
        this.requestRender();
    }

    /** text text text text text (text text text text text) */
    clearCacheAndRender() {
        this._tileCache.clear();
        this._tileLoading.clear();
        this._tileFadeStart.clear();
        this._loadQueue = [];
        this._loadQueuedKeys.clear();
        this._activeLoads = 0;
        this.requestRender();
    }

    // ── text text ──

    setDetectionResults(cells, roiPolygons = null) {
        let filtered = cells || [];

        // ROI text text text text text text
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

        // text text text (text text O(1) text)
        this._spatialGrid = new SpatialGrid(2048);
        this._spatialGrid.build(filtered);

        this._heatmapDirty = true;
        this._heatmapImage = null;
        this._buildHeatmapCache();
        this.requestRender();
    }

    setHiddenDetectionResults(cells, roiPolygons = null) {
        let filtered = cells || [];

        if (roiPolygons && roiPolygons.length > 0) {
            filtered = filtered.filter(c =>
                roiPolygons.some(poly => this._pointInPolygon(c.x, c.y, poly))
            );
        }

        this.hiddenDetectionCells = filtered.map(c => ({
            ...c,
            hidden: true,
            exclude_from_score: true,
        }));
        this._highlightedHiddenCellIdxSet = null;
        this._hiddenSpatialGrid = new SpatialGrid(2048);
        this._hiddenSpatialGrid.build(this.hiddenDetectionCells);
        this.requestRender();
    }

    // ── Cell editing (Alt+Click) ──

    /**
     * text text(WSI text)text text text text text.
     * @param {number} sx WSI x
     * @param {number} sy WSI y
     * @param {number} maxScreenPx text text text text text
     * @returns {{index, cell}|null}
     */
    _findNearestCell(sx, sy, maxScreenPx = 30) {
        if (!this.detectionCells.length) return null;
        const maxDistWsi = this.zoom > 0 ? maxScreenPx / this.zoom : maxScreenPx;
        const r = maxDistWsi;

        // SpatialGridtext text text
        let candidates;
        if (this._spatialGrid) {
            const cellsInBox = this._spatialGrid.query(sx - r, sy - r, sx + r, sy + r);
            // SpatialGridtext cell text text → text text text
            candidates = cellsInBox.map(c => ({ cell: c, index: this.detectionCells.indexOf(c) }));
        } else {
            candidates = this.detectionCells.map((c, i) => ({ cell: c, index: i }));
        }

        let bestIdx = -1;
        let bestCell = null;
        let bestDist = Infinity;
        for (const { cell, index } of candidates) {
            // visibility/confidence text (text text text text text)
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

    _cellAnnotationEditModeActive() {
        return Boolean(this.cellAnnotationPatchViewActive && Array.isArray(this.annotations) && this.annotations.length);
    }

    _annotationCellCenter(annotation) {
        const center = annotation?.cell_center || annotation?.properties?.cell_center;
        if (Array.isArray(center) && center.length >= 2) {
            const x = Number(center[0]);
            const y = Number(center[1]);
            if (Number.isFinite(x) && Number.isFinite(y) && (x || y)) return [x, y];
        }
        const bbox = annotation?.cell_bbox || annotation?.properties?.cell_bbox || {};
        const bx = Number(bbox.x ?? bbox.x0);
        const by = Number(bbox.y ?? bbox.y0);
        const bw = Number(bbox.width ?? (Number(bbox.x1) - bx));
        const bh = Number(bbox.height ?? (Number(bbox.y1) - by));
        if (Number.isFinite(bx) && Number.isFinite(by) && Number.isFinite(bw) && Number.isFinite(bh)) {
            return [bx + bw / 2, by + bh / 2];
        }
        const coords = Array.isArray(annotation?.coordinates) ? annotation.coordinates : [];
        const points = coords
            .map(point => Array.isArray(point) ? [Number(point[0]), Number(point[1])] : null)
            .filter(point => point && Number.isFinite(point[0]) && Number.isFinite(point[1]));
        if (!points.length) return null;
        const xs = points.map(point => point[0]);
        const ys = points.map(point => point[1]);
        return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
    }

    _findNearestCellAnnotation(sx, sy, maxScreenPx = 30) {
        if (!this._cellAnnotationEditModeActive()) return null;
        const maxDistWsi = this.zoom > 0 ? maxScreenPx / this.zoom : maxScreenPx;
        let bestIdx = -1;
        let bestAnn = null;
        let bestDist = Infinity;
        for (let i = 0; i < this.annotations.length; i++) {
            const ann = this.annotations[i];
            if (!ann || ann.visible === false) continue;
            const center = this._annotationCellCenter(ann);
            if (!center) continue;
            const d = Math.hypot(center[0] - sx, center[1] - sy);
            if (d < bestDist) {
                bestDist = d;
                bestIdx = i;
                bestAnn = ann;
            }
        }
        return bestIdx >= 0 && bestDist <= maxDistWsi ? { index: bestIdx, cell: bestAnn } : null;
    }

    /** Ray-casting point-in-polygon (scene text) */
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

    /** text text text text text text text (visibility/confidence text text) */
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

    _findCellAnnotationsInPolygon(poly) {
        if (!this._cellAnnotationEditModeActive() || poly.length < 3) return [];
        const list_result = [];
        for (let i = 0; i < this.annotations.length; i++) {
            const ann = this.annotations[i];
            if (!ann || ann.visible === false) continue;
            const center = this._annotationCellCenter(ann);
            if (!center) continue;
            if (this._pointInPolygon(center[0], center[1], poly)) list_result.push(i);
        }
        return list_result;
    }

    _findHiddenCellsInPolygon(poly) {
        if (!this.hiddenDetectionCells.length || poly.length < 3) return [];
        let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
        for (const [x, y] of poly) {
            if (x < xMin) xMin = x;
            if (x > xMax) xMax = x;
            if (y < yMin) yMin = y;
            if (y > yMax) yMax = y;
        }

        let candidates;
        if (this._hiddenSpatialGrid) {
            const cellsInBox = this._hiddenSpatialGrid.query(xMin, yMin, xMax, yMax);
            candidates = cellsInBox.map(c => ({ cell: c, index: this.hiddenDetectionCells.indexOf(c) }));
        } else {
            candidates = this.hiddenDetectionCells.map((c, i) => ({ cell: c, index: i }));
        }

        const list_result = [];
        const thresh = this.defaultConfidence ?? 0.01;
        for (const { cell, index } of candidates) {
            if (index < 0) continue;
            if ((cell.confidence ?? 1.0) < thresh) continue;
            if (this._pointInPolygon(cell.x, cell.y, poly)) list_result.push(index);
        }
        return list_result;
    }

    _pushUndoOp(op) {
        this._undoStack.push(op);
        if (this._undoStack.length > this._maxUndo) this._undoStack.shift();
        this._redoStack = [];
    }

    deleteCell(cellIdx) {
        if (!this.canEditDetectionResults) return;
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
        if (!this.canEditDetectionResults) return;
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
     * text text detectionCells text text — Shift+click UX text.
     * confidence text 1.0 (text text text max). undo/redo text.
     * highlight text text text text — text text text text text text text text text text text.
     * text: text text text.
     */
    addCell(sx, sy, classId, className = null) {
        if (!this.canEditDetectionResults) return null;
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
        // text highlight text text text text text text text.
        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._refreshAfterCellEdit();
        return cell;
    }

    /** text text text text */
    deleteCells(listIndices) {
        if (!this.canEditDetectionResults) return;
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

    /** text text text text text */
    changeCellsClass(listIndices, newClassId, newClassName = null) {
        if (!this.canEditDetectionResults) return;
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

    promoteHiddenCells(listIndices, newClassId, newClassName = null) {
        if (!this.canEditDetectionResults) return [];
        if (!listIndices || listIndices.length === 0) return [];
        const list_valid = [...new Set(listIndices)]
            .filter(i => i >= 0 && i < this.hiddenDetectionCells.length)
            .sort((a, b) => a - b);
        if (list_valid.length === 0) return [];

        const startIndex = this.detectionCells.length;
        const hiddenItems = list_valid.map(i => ({
            index: i,
            cell: { ...this.hiddenDetectionCells[i] },
        }));
        const promoted = list_valid.map(i => {
            const src = this.hiddenDetectionCells[i];
            const cell = {
                x: Number(src.x),
                y: Number(src.y),
                confidence: src.confidence ?? 1.0,
                class_id: Number(newClassId),
                class_name: newClassName || `Class ${newClassId}`,
            };
            return cell;
        });

        this._pushUndoOp({
            type: 'promoteHidden',
            items: promoted.map((cell, offset) => ({ index: startIndex + offset, cell })),
            hiddenItems,
        });

        const removeSet = new Set(list_valid);
        this.hiddenDetectionCells = this.hiddenDetectionCells.filter((_, i) => !removeSet.has(i));
        this._hiddenSpatialGrid = new SpatialGrid(2048);
        this._hiddenSpatialGrid.build(this.hiddenDetectionCells);

        this.detectionCells.push(...promoted);
        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._highlightedHiddenCellIdxSet = null;
        this._refreshAfterCellEdit();
        return promoted;
    }

    /** text text text text */
    undoCellEdit() {
        if (!this.canEditDetectionResults) return false;
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
            // text text = text text splice (text text text).
            const sortedDesc = [...op.items].sort((a, b) => b.index - a.index);
            for (const { index } of sortedDesc) {
                if (index < 0 || index >= this.detectionCells.length) continue;
                this.detectionCells.splice(index, 1);
            }
        } else if (op.type === 'promoteHidden') {
            const visibleDesc = [...op.items].sort((a, b) => b.index - a.index);
            for (const { index } of visibleDesc) {
                if (index < 0 || index >= this.detectionCells.length) continue;
                this.detectionCells.splice(index, 1);
            }
            const hiddenAsc = [...(op.hiddenItems || [])].sort((a, b) => a.index - b.index);
            for (const { index, cell } of hiddenAsc) {
                const clamped = Math.max(0, Math.min(index, this.hiddenDetectionCells.length));
                this.hiddenDetectionCells.splice(clamped, 0, cell);
            }
            this._hiddenSpatialGrid = new SpatialGrid(2048);
            this._hiddenSpatialGrid.build(this.hiddenDetectionCells);
        }
        this._redoStack.push(op);
        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._refreshAfterCellEdit();
        return true;
    }

    /** text undo text */
    redoCellEdit() {
        if (!this.canEditDetectionResults) return false;
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
        } else if (op.type === 'promoteHidden') {
            const removeSet = new Set((op.hiddenItems || []).map(it => it.index));
            this.hiddenDetectionCells = this.hiddenDetectionCells.filter((_, i) => !removeSet.has(i));
            this._hiddenSpatialGrid = new SpatialGrid(2048);
            this._hiddenSpatialGrid.build(this.hiddenDetectionCells);
            const visibleAsc = [...op.items].sort((a, b) => a.index - b.index);
            for (const { index, cell } of visibleAsc) {
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

    clearHiddenCellHighlight() {
        if (this._highlightedHiddenCellIdxSet) {
            this._highlightedHiddenCellIdxSet = null;
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
        // text text text text text text
        const cls = new Set(this.detectionCells.map(c => c.class_id));
        cls.forEach(id => {
            if (this.classVisibility[id] === undefined) this.classVisibility[id] = true;
            if (this.classConfidence[id] === undefined) this.classConfidence[id] = this.defaultConfidence ?? 0.01;
        });

        // text text + text text text
        this._spatialGrid = new SpatialGrid(2048);
        this._spatialGrid.build(this.detectionCells);
        this._heatmapDirty = true;
        this._heatmapImage = null;
        this._buildHeatmapCache();
        this.requestRender();

        if (this.onCellEdited) this.onCellEdited();
    }

    /**
     * text density text text text (text TiledDetectionOverlay._build_heatmap_cache)
     * text text 2048 text text histogram2d
     * confidence text text text
     */
    /**
     * text density text text text — setDetectionResults text 1text text
     * text text: confidence text text text text density text
     * confidence/visibility text text text text text text (text text)
     */
    _buildHeatmapCache() {
        this._heatmapCache = null;
        if (!this.detectionCells.length || !this.slideInfo) return;

        // text text text
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

        // text density text (confidence text text)
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
     * text text (5x5 box blur text text)
     * text: cv2.GaussianBlur(sigma = max(3.0, w/60)) ≈ sigma 8~9
     * 5x5 box blur × passes text → sigma ≈ sqrt(passes * 2) text text
     * passes=18 → sigma ≈ 6, passes=32 → sigma ≈ 8
     */
    _blurGrid(src, w, h, passes) {
        let a = new Float32Array(src);
        let b = new Float32Array(w * h);
        for (let p = 0; p < passes; p++) {
            // text 5-tap text: [1,2,3,2,1]/9 text text → text 5-tap
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
            // text 5-tap text
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

    /** jet text: 0~1 → [r, g, b] */
    _jetColor(t) {
        t = Math.max(0, Math.min(1, t));
        let r, g, b;
        if (t < 0.25) { r = 0; g = t * 4; b = 1; }
        else if (t < 0.5) { r = 0; g = 1; b = 1 - (t - 0.25) * 4; }
        else if (t < 0.75) { r = (t - 0.5) * 4; g = 1; b = 0; }
        else { r = 1; g = 1 - (t - 0.75) * 4; b = 0; }
        return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
    }

    // ── Segmentation text (text wsi_view_widget.py text) ──
    // text: Stroma=text, Non_Tumor=text, Tumor=text, alpha=128

    /**
     * Segmentation text text
     * @param {Uint8Array} maskData - text text text (0=BG, 1=Stroma, 2=Non_Tumor, 3=Tumor)
     * @param {number} maskW - text text
     * @param {number} maskH - text text
     * @param {number} sceneX - WSI level-0 offset X
     * @param {number} sceneY - WSI level-0 offset Y
     * @param {number} sceneW - WSI level-0 text text
     * @param {number} sceneH - WSI level-0 text text
     * @param {string[]} classNames - ['Stroma', 'Non_Tumor', 'Tumor']
     */
    setSegmentationOverlay(maskData, maskW, maskH, sceneX, sceneY, sceneW, sceneH, classNames) {
        // text text text: Stroma=text, Non_Tumor=text, Tumor=text
        const SEG_COLORS = {
            1: [255, 0, 0, 128],    // Stroma
            2: [0, 255, 0, 128],    // Non_Tumor
            3: [0, 0, 255, 128],    // Tumor
        };

        // RGBA ImageData text
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
     * base64 text seg overlay text text (text text text)
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
     * Virtual Stain (VS IHC) text text — text text text.
     * @param {object} meta - {
     *   slide_id, stain_type, target_mpp,
     *   roi_origin: [x,y], canvas_l0_w, canvas_l0_h,
     *   tile_size, levels: [{level,width,height,nx,ny}...],
     *   roi_polygons? (text text)
     * }
     */
    setVirtualStainOverlay(meta) {
        // text text text text
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
        if (!this.detectionCells.length && !this._highlightedHiddenCellIdxSet &&
                !(this._lassoActive && this._cellAnnotationEditModeActive())) return;

        // effectiveMpp text: text text text text text
        // mpp < 3.0 → text text, mpp >= 3.0 → text → text
        const effectiveMpp = this.getEffectiveMpp();
        if (this.detectionCells.length) {
            if (effectiveMpp >= 3.0) {
                this._renderHeatmap(octx);
            } else {
                this._renderCells(octx);
            }
        }

        // text text text text text text text text
        this._renderCellHighlight(octx);
        this._renderMultiCellHighlight(octx);
        this._renderHiddenCellHighlight(octx);
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

    _renderHiddenCellHighlight(octx) {
        if (!this._highlightedHiddenCellIdxSet || this._highlightedHiddenCellIdxSet.size === 0) return;
        const baseR = Math.max(10, 6 * this.zoom);
        octx.save();
        for (const idx of this._highlightedHiddenCellIdxSet) {
            if (idx < 0 || idx >= this.hiddenDetectionCells.length) continue;
            const c = this.hiddenDetectionCells[idx];
            const [hx, hy] = this.sceneToCanvas(c.x, c.y);

            octx.strokeStyle = 'rgba(17,24,39,0.85)';
            octx.lineWidth = 4;
            octx.beginPath();
            octx.arc(hx, hy, baseR + 1, 0, Math.PI * 2);
            octx.stroke();

            octx.fillStyle = 'rgba(156,163,175,0.32)';
            octx.beginPath();
            octx.arc(hx, hy, baseR, 0, Math.PI * 2);
            octx.fill();

            octx.strokeStyle = '#9CA3AF';
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

        // text text text text text text (text 18px)
        const baseR = Math.max(18, 12 * this.zoom);

        octx.save();

        // text text text (text)
        octx.strokeStyle = 'rgba(0,0,0,0.85)';
        octx.lineWidth = 6;
        octx.beginPath();
        octx.arc(hx, hy, baseR + 2, 0, Math.PI * 2);
        octx.stroke();

        // text
        octx.fillStyle = `rgba(${r},${g},${b},0.25)`;
        octx.beginPath();
        octx.arc(hx, hy, baseR, 0, Math.PI * 2);
        octx.fill();

        // text text text
        octx.strokeStyle = `rgb(${r},${g},${b})`;
        octx.lineWidth = 3;
        octx.shadowColor = `rgb(${r},${g},${b})`;
        octx.shadowBlur = 10;
        octx.beginPath();
        octx.arc(hx, hy, baseR, 0, Math.PI * 2);
        octx.stroke();

        // text (text text text text)
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
     * text text (text create_heatmap_masktext text text)
     * 1. text text densitytext text
     * 2. text text text crop
     * 3. text text
     * 4. jet text + text ImageDatatext text
     */
    _renderHeatmap(octx) {
        const cache = this._heatmapCache;
        if (!cache) return;

        // text text text — text text
        const visKey = Object.keys(cache.clsDensities)
            .filter(k => this.classVisibility[parseInt(k)] !== false)
            .sort()
            .join(',');

        // text text text text drawImage
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
     * text text text text text text 1text text.
     * text/text text text text drawImagetext text.
     */
    _buildHeatmapImage(visKey) {
        const cache = this._heatmapCache;
        if (!cache) return null;
        const { clsDensities, xMin, yMin, gw, gh, sx, sy } = cache;

        // text text text (text text)
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

        // text text (text 512px)
        const maxDim = 512;
        let outW, outH;
        if (gw >= gh) {
            outW = Math.min(maxDim, gw);
            outH = Math.max(1, Math.round(outW * gh / gw));
        } else {
            outH = Math.min(maxDim, gh);
            outW = Math.max(1, Math.round(outH * gw / gh));
        }

        // text (nearest)
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

        // text text
        const blurPasses = Math.max(8, Math.round(outW / 20));
        const blurred = this._blurGrid(resized, outW, outH, blurPasses);

        let maxVal = 0;
        for (let i = 0; i < blurred.length; i++) {
            if (blurred[i] > maxVal) maxVal = blurred[i];
        }
        if (maxVal === 0) return null;

        // ImageData → text text
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

        // SpatialGridtext text text text text (O(1), text text text)
        const visible = this._spatialGrid.query(viewLeft, viewTop, viewRight, viewBottom);

        // effectiveMpptext text text text/text text
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
            const rawColor = (override && override[cell.class_id]) ||
                cell.color ||
                cell.class_color ||
                cell.properties?.color ||
                CLASS_COLORS[cell.class_id] ||
                '#00FF00';
            const color = Array.isArray(rawColor)
                ? `rgb(${rawColor.slice(0, 3).map(v => Math.max(0, Math.min(255, Number(v) || 0))).join(',')})`
                : String(rawColor || '#00FF00');
            const coords = Array.isArray(cell.coordinates) ? cell.coordinates : [];
            if (coords.length >= 2) {
                octx.beginPath();
                coords.forEach((point, idx) => {
                    const [px, py] = Array.isArray(point)
                        ? this.sceneToCanvas(Number(point[0]), Number(point[1]))
                        : this.sceneToCanvas(Number(point.x), Number(point.y));
                    if (idx === 0) octx.moveTo(px, py);
                    else octx.lineTo(px, py);
                });
                if (coords.length >= 3) octx.closePath();
                octx.strokeStyle = color;
                octx.stroke();
                continue;
            }
            if (cell.bbox && Number.isFinite(Number(cell.bbox.x)) && Number.isFinite(Number(cell.bbox.y))) {
                const bx = Number(cell.bbox.x);
                const by = Number(cell.bbox.y);
                const bw = Math.max(1, Number(cell.bbox.width || 0));
                const bh = Math.max(1, Number(cell.bbox.height || 0));
                const [rx, ry] = this.sceneToCanvas(bx, by);
                octx.strokeStyle = color;
                octx.strokeRect(rx, ry, bw * this.zoom, bh * this.zoom);
                continue;
            }

            octx.beginPath();
            octx.arc(cx, cy, cellRadius, 0, Math.PI * 2);
            octx.strokeStyle = color;
            octx.stroke();
        }

    }

    // ── Annotation text ──

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

    setAnnotationDisplayStyle(style = {}) {
        if (style.strokeWidth != null) {
            const value = Number(style.strokeWidth);
            if (Number.isFinite(value)) this.annotationStrokeWidth = Math.max(1, Math.min(12, value));
        }
        if (style.fillOpacity != null) {
            const value = Number(style.fillOpacity);
            if (Number.isFinite(value)) this.annotationFillOpacity = Math.max(0, Math.min(0.8, value));
        }
        this.requestRender();
    }

    setAnnotationDrawColor(color = [0, 255, 0]) {
        if (Array.isArray(color)) {
            const rgb = color.slice(0, 3).map(v => Math.max(0, Math.min(255, Number(v) || 0)));
            this.annotationDrawColor = rgb.length === 3 ? rgb : [0, 255, 0];
        } else if (typeof color === 'string') {
            const m = color.match(/^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
            this.annotationDrawColor = m
                ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)]
                : [0, 255, 0];
        }
        this.requestRender();
    }

    setHiddenAnnotationClassIds(ids = []) {
        this.hiddenAnnotationClassIds = new Set((Array.isArray(ids) ? ids : []).map(String).filter(Boolean));
        this.requestRender();
    }

    _annotationClassId(ann) {
        return String(ann?.class_id || ann?.properties?.class_id || '');
    }

    _isAnnotationClassHidden(ann) {
        const classId = this._annotationClassId(ann);
        return Boolean(classId && this.hiddenAnnotationClassIds?.has(classId));
    }

    /**
     * text text text 1mm text text px text. mpp(µm/px) text 0.25 text 4000 px = 1mm.
     * slideInfo text text mpp text text null — text text text text.
     */
    _pixelsPerMM() {
        if (!this.slideInfo || !this.slideInfo.mpp) return null;
        return 1000 / this.slideInfo.mpp;  // 1mm = 1000 µm
    }

    /** text(cx,cy) text 1mm × 1mm text 4 text (scene text). */
    _makeRect1mm2Coords(cx, cy) {
        const ppm = this._pixelsPerMM();
        if (ppm == null) return null;
        const half = ppm / 2;  // 1mm text text
        return [
            [cx - half, cy - half],
            [cx + half, cy - half],
            [cx + half, cy + half],
            [cx - half, cy + half],
        ];
    }

    /** text(cx,cy) text text 1mm² text text 64text text (scene text). */
    _makeCircle1mm2Coords(cx, cy) {
        const ppm = this._pixelsPerMM();
        if (ppm == null) return null;
        // text = π r² = 1mm²  →  r = √(1/π) mm  →  px text text
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
            // text text text, text text text, text text
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
            // text text text 1mm × 1mm text text text.
            const coords = this._makeRect1mm2Coords(sx, sy);
            if (coords) this._createAnnotation('rectangle', coords);
        } else if (this.drawMode === 'circle-1mm2') {
            // text 1mm² text (64text text) — text polygon text text text
            // text/ROI text/text text text text.
            const coords = this._makeCircle1mm2Coords(sx, sy);
            if (coords) this._createAnnotation('polygon', coords);
        } else if (this.drawMode === 'ruler') {
            // 1text text: text, 2text text: text, 3text text: text text text.
            // annotation text text X — drawMode text text text text text.
            if (!this._rulerStart || this._rulerFinalized) {
                this._rulerStart = [sx, sy];
                this._rulerEnd = [sx, sy];
                this._rulerFinalized = false;
            } else {
                // text/text ±2° text — preview text text text text.
                this._rulerEnd = this._snapRulerEnd(
                    this._rulerStart[0], this._rulerStart[1], sx, sy);
                this._rulerFinalized = true;
            }
            this.requestRender();
        }
    }

    _onDrawMouseMove(sx, sy, cx, cy) {
        this._drawingCurrent = [sx, sy];

        // text text text text (10px text)
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
            // text text text text (text 3text)
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
                this._createAnnotation('polygon', brushPolygon, { source: 'brush' });
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
            // text(self-intersection) text — text text text
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

    /** text text text text text text */
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

        const rasterPolygon = this._makeRasterBrushPolygon(path, radius);
        if (rasterPolygon && rasterPolygon.length >= 3) return rasterPolygon;

        return this._makeOffsetBrushPolygon(path, radius);
    }

    _makeOffsetBrushPolygon(path, radius) {
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

    _makeRasterBrushPolygon(path, radius) {
        if (typeof document === 'undefined' || !path || path.length < 2 || radius <= 0) return null;

        const pad = radius + 2;
        const xs = path.map(p => p[0]);
        const ys = path.map(p => p[1]);
        const minX = Math.min(...xs) - pad;
        const minY = Math.min(...ys) - pad;
        const maxX = Math.max(...xs) + pad;
        const maxY = Math.max(...ys) + pad;
        const widthScene = Math.max(1, maxX - minX);
        const heightScene = Math.max(1, maxY - minY);
        const maxSide = 1400;
        let scale = 14 / radius;
        scale = Math.min(scale, maxSide / Math.max(widthScene, heightScene));
        if (!Number.isFinite(scale) || scale <= 0) return null;

        const width = Math.max(4, Math.ceil(widthScene * scale) + 2);
        const height = Math.max(4, Math.ceil(heightScene * scale) + 2);
        if (width > maxSide + 4 || height > maxSide + 4 || radius * scale < 2) return null;

        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) return null;

        ctx.clearRect(0, 0, width, height);
        ctx.beginPath();
        ctx.moveTo((path[0][0] - minX) * scale, (path[0][1] - minY) * scale);
        for (let i = 1; i < path.length; i++) {
            ctx.lineTo((path[i][0] - minX) * scale, (path[i][1] - minY) * scale);
        }
        ctx.strokeStyle = '#000';
        ctx.lineWidth = Math.max(2, radius * 2 * scale);
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.stroke();

        const image = ctx.getImageData(0, 0, width, height).data;
        const mask = new Uint8Array(width * height);
        for (let i = 0, p = 0; i < image.length; i += 4, p++) {
            mask[p] = image[i + 3] > 0 ? 1 : 0;
        }

        const loop = this._traceLargestMaskLoop(mask, width, height);
        if (!loop || loop.length < 3) return null;
        const simplified = this._simplifyPolylineRdp(loop, 1.2);
        const scene = simplified.map(p => [p[0] / scale + minX, p[1] / scale + minY]);
        return this._cleanPolygonPoints(scene);
    }

    _traceLargestMaskLoop(mask, width, height) {
        const filled = (x, y) => x >= 0 && y >= 0 && x < width && y < height && mask[y * width + x];
        const segments = [];
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                if (!filled(x, y)) continue;
                if (!filled(x, y - 1)) segments.push({ a: [x, y], b: [x + 1, y] });
                if (!filled(x + 1, y)) segments.push({ a: [x + 1, y], b: [x + 1, y + 1] });
                if (!filled(x, y + 1)) segments.push({ a: [x + 1, y + 1], b: [x, y + 1] });
                if (!filled(x - 1, y)) segments.push({ a: [x, y + 1], b: [x, y] });
            }
        }
        if (!segments.length) return null;

        const key = (p) => `${p[0]},${p[1]}`;
        const starts = new Map();
        segments.forEach((seg, index) => {
            const k = key(seg.a);
            if (!starts.has(k)) starts.set(k, []);
            starts.get(k).push(index);
        });

        const used = new Set();
        const loops = [];
        for (let i = 0; i < segments.length; i++) {
            if (used.has(i)) continue;
            const startKey = key(segments[i].a);
            const loop = [segments[i].a];
            let current = segments[i].b;
            used.add(i);
            let guard = 0;
            while (guard < segments.length + 2) {
                loop.push(current);
                const currentKey = key(current);
                if (currentKey === startKey) break;
                const candidates = starts.get(currentKey) || [];
                const nextIndex = candidates.find(index => !used.has(index));
                if (nextIndex == null) break;
                used.add(nextIndex);
                current = segments[nextIndex].b;
                guard++;
            }
            if (key(loop[loop.length - 1]) === startKey) {
                loop.pop();
                const clean = this._removeCollinearGridPoints(loop);
                if (clean.length >= 3) loops.push(clean);
            }
        }
        if (!loops.length) return null;
        loops.sort((a, b) => Math.abs(this._polygonSignedArea(b)) - Math.abs(this._polygonSignedArea(a)));
        return loops[0];
    }

    _removeCollinearGridPoints(points) {
        const clean = this._cleanPolylinePoints(points);
        let changed = true;
        while (changed && clean.length > 3) {
            changed = false;
            for (let i = clean.length - 1; i >= 0; i--) {
                const prev = clean[(i - 1 + clean.length) % clean.length];
                const curr = clean[i];
                const next = clean[(i + 1) % clean.length];
                const cross = (curr[0] - prev[0]) * (next[1] - curr[1]) - (curr[1] - prev[1]) * (next[0] - curr[0]);
                if (Math.abs(cross) < 1e-9) {
                    clean.splice(i, 1);
                    changed = true;
                }
            }
        }
        return clean;
    }

    _simplifyPolylineRdp(points, tolerance) {
        if (!points || points.length <= 3 || tolerance <= 0) return points || [];
        const closed = points.concat([points[0]]);
        const simplified = this._simplifyOpenPolylineRdp(closed, tolerance);
        simplified.pop();
        return simplified.length >= 3 ? simplified : points;
    }

    _simplifyOpenPolylineRdp(points, tolerance) {
        if (points.length <= 2) return points;
        let maxDistance = 0;
        let index = -1;
        const start = points[0];
        const end = points[points.length - 1];
        for (let i = 1; i < points.length - 1; i++) {
            const distance = this._pointToSegmentDistance(points[i], start, end);
            if (distance > maxDistance) {
                maxDistance = distance;
                index = i;
            }
        }
        if (maxDistance <= tolerance || index < 0) return [start, end];
        const left = this._simplifyOpenPolylineRdp(points.slice(0, index + 1), tolerance);
        const right = this._simplifyOpenPolylineRdp(points.slice(index), tolerance);
        return left.slice(0, -1).concat(right);
    }

    _pointToSegmentDistance(p, a, b) {
        const dx = b[0] - a[0];
        const dy = b[1] - a[1];
        const len2 = dx * dx + dy * dy;
        if (len2 < 1e-12) return Math.hypot(p[0] - a[0], p[1] - a[1]);
        const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2));
        return Math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dy * t));
    }

    _isSelfIntersecting(pts) {
        const n = pts.length;
        if (n < 4) return false; // text text text
        // text text text text(edge) text text
        for (let i = 0; i < n; i++) {
            const a = pts[i], b = pts[(i + 1) % n];
            for (let j = i + 2; j < n; j++) {
                if (i === 0 && j === n - 1) continue; // text text (text-text) text
                const c = pts[j], d = pts[(j + 1) % n];
                if (this._segmentsIntersect(a, b, c, d)) return true;
            }
        }
        return false;
    }

    /** text text (p1-p2, p3-p4) text text */
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
        // Ruler text text text text (text text/text text text text).
        this._rulerStart = null;
        this._rulerEnd = null;
        this._rulerFinalized = false;
        this.requestRender();
    }

    _createAnnotation(type, coordinates, options = {}) {
        this.pushAnnotationUndo();
        this._annotationCounter++;
        const COLORS = { polygon: [0, 255, 0], rectangle: [255, 0, 0], point: [0, 0, 255] };
        const drawColor = Array.isArray(options.color)
            ? options.color.slice(0, 3)
            : (Array.isArray(this.annotationDrawColor) ? this.annotationDrawColor.slice(0, 3) : COLORS[type]);
        const ann = {
            id: crypto.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            name: String(this._annotationCounter),
            type,
            coordinates,
            color: drawColor || COLORS[type],
            visible: true,
            selected: false,
            source: options.source || '',
            properties: {
                ...(options.properties || {}),
                source: options.source || options.properties?.source || '',
            },
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

    // ── Annotation text ──

    _renderAnnotations(octx) {
        const halfVW = this._viewW / Math.max(this.zoom, 0.0001) / 2;
        const halfVH = this._viewH / Math.max(this.zoom, 0.0001) / 2;
        const viewLeft = this.viewCenterX - halfVW;
        const viewTop = this.viewCenterY - halfVH;
        const viewRight = this.viewCenterX + halfVW;
        const viewBottom = this.viewCenterY + halfVH;
        const intersectsView = (ann) => {
            if (ann.selected) return true;
            const bbox = ann.properties?.cell_bbox || ann.cell_bbox || ann.bbox;
            if (bbox && typeof bbox === 'object') {
                const x0 = Number(bbox.x0 ?? bbox.x ?? 0);
                const y0 = Number(bbox.y0 ?? bbox.y ?? 0);
                const x1 = Number(bbox.x1 ?? (x0 + Number(bbox.width ?? 0)));
                const y1 = Number(bbox.y1 ?? (y0 + Number(bbox.height ?? 0)));
                if ([x0, y0, x1, y1].every(Number.isFinite)) {
                    return x1 >= viewLeft && x0 <= viewRight && y1 >= viewTop && y0 <= viewBottom;
                }
            }
            const coords = Array.isArray(ann.coordinates) ? ann.coordinates : [];
            if (!coords.length) return true;
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            for (const pt of coords) {
                const x = Number(pt?.[0]);
                const y = Number(pt?.[1]);
                if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
                if (x < minX) minX = x;
                if (y < minY) minY = y;
                if (x > maxX) maxX = x;
                if (y > maxY) maxY = y;
            }
            if (!Number.isFinite(minX)) return true;
            return maxX >= viewLeft && minX <= viewRight && maxY >= viewTop && minY <= viewBottom;
        };
        // text annotation
        for (const ann of this.annotations) {
            if (!ann.visible) continue;
            if (this._isAnnotationClassHidden(ann)) continue;
            const [r, g, b] = ann.color;
            const strokeColor = `rgb(${r},${g},${b})`;
            const fillOpacity = Math.max(0, Math.min(0.8, Number(this.annotationFillOpacity ?? 0.1)));
            const strokeWidth = Math.max(1, Math.min(12, Number(this.annotationStrokeWidth ?? 2)));
            const fillColor = `rgba(${r},${g},${b},${fillOpacity})`;
            const lineWidth = ann.selected ? strokeWidth + 1 : strokeWidth;
            const isCellAnnotation = ann.source === 'patch_cell_annotation' ||
                ann.source === 'wsi_labeling_assistance' ||
                ann.properties?.source === 'patch_cell_annotation' ||
                ann.properties?.source === 'wsi_labeling_assistance' ||
                Boolean(this.cellAnnotationPatchViewActive && ann.type === 'rectangle');
            if (isCellAnnotation && !intersectsView(ann)) continue;

            if (isCellAnnotation && this.cellAnnotationDisplayMode === 'point') {
                const center = ann.properties?.cell_center || ann.cell_center || ann.center ||
                    (Array.isArray(ann.coordinates) && ann.coordinates.length
                        ? [
                            ann.coordinates.reduce((sum, pt) => sum + Number(pt?.[0] || 0), 0) / ann.coordinates.length,
                            ann.coordinates.reduce((sum, pt) => sum + Number(pt?.[1] || 0), 0) / ann.coordinates.length,
                        ]
                        : null);
                if (Array.isArray(center) && center.length >= 2) {
                    this._drawCellAnnotationPoint(octx, Number(center[0]), Number(center[1]), [r, g, b], ann.selected);
                    continue;
                }
            }

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

        // text text text text
        this._renderInsertVertexPreview(octx);
        this._renderMergeHover(octx);
        this._renderDrawingPreview(octx);
    }

    _drawCellAnnotationPoint(octx, sx, sy, color, selected = false) {
        if (!Number.isFinite(sx) || !Number.isFinite(sy)) return;
        const [cx, cy] = this.sceneToCanvas(sx, sy);
        const effectiveMpp = this.getEffectiveMpp();
        const baseRadius = effectiveMpp < 1.0 ? 8 : 5;
        const radius = Math.max(2, baseRadius * this.zoom);
        const [r, g, b] = color || [0, 255, 0];
        octx.save();
        if (selected) {
            octx.strokeStyle = 'rgba(0,0,0,0.85)';
            octx.lineWidth = 3;
            octx.beginPath();
            octx.arc(cx, cy, radius + 2, 0, Math.PI * 2);
            octx.stroke();
        }
        octx.lineWidth = effectiveMpp < 1.0 ? 2 : 1.2;
        octx.strokeStyle = `rgb(${r},${g},${b})`;
        octx.beginPath();
        octx.arc(cx, cy, radius, 0, Math.PI * 2);
        octx.stroke();
        if (selected) {
            octx.fillStyle = `rgba(${r},${g},${b},0.22)`;
            octx.beginPath();
            octx.arc(cx, cy, radius, 0, Math.PI * 2);
            octx.fill();
        }
        octx.restore();
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
        if (!ann || !ann.visible || this._isAnnotationClassHidden(ann)) return;
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
     * scene text text text text text text text text text text.
     *  - 1 mm text: "342.7 µm (1,370 px)"
     *  - 1 mm text: "1.234 mm (4,936 px)"
     * mpp text text px text.
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
     * text→text text text/text ±2° text text text text.
     * text text text — text text text text text text text text.
     * text: [snappedSx, snappedSy]
     */
    _snapRulerEnd(sx0, sy0, sx1, sy1) {
        const dx = sx1 - sx0;
        const dy = sy1 - sy0;
        if (dx === 0 && dy === 0) return [sx1, sy1];
        const FLOAT_SNAP_DEG = 2;
        const float_tol = FLOAT_SNAP_DEG * Math.PI / 180;
        const float_ang = Math.atan2(dy, dx);  // (-π, π]
        const float_abs = Math.abs(float_ang);
        // text: 0 text ±π
        if (float_abs < float_tol || Math.abs(float_abs - Math.PI) < float_tol) {
            return [sx1, sy0];
        }
        // text: ±π/2
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

        // text text
        octx.beginPath();
        octx.moveTo(cx0, cy0);
        octx.lineTo(cx1, cy1);
        octx.strokeStyle = color;
        octx.lineWidth = 2;
        if (!this._rulerFinalized) octx.setLineDash([6, 3]);
        octx.stroke();
        octx.setLineDash([]);

        // text text text
        for (const [px, py] of [[cx0, cy0], [cx1, cy1]]) {
            octx.beginPath();
            octx.arc(px, py, 4, 0, Math.PI * 2);
            octx.fillStyle = color;
            octx.fill();
            octx.strokeStyle = '#fff';
            octx.lineWidth = 1.5;
            octx.stroke();
        }

        // text text — text text text + text
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
        // text text text text text text (text text text text)
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
        // text text (text text text text)
        octx.textAlign = 'start';
        octx.textBaseline = 'alphabetic';
    }

    _renderDrawingPreview(octx) {
        const [pr, pg, pb] = Array.isArray(this.annotationDrawColor) ? this.annotationDrawColor : [0, 255, 0];
        const previewStroke = `rgba(${pr},${pg},${pb},0.82)`;
        const previewStrokeStrong = `rgba(${pr},${pg},${pb},0.95)`;
        const previewFill = `rgba(${pr},${pg},${pb},0.10)`;
        const previewFillStrong = `rgba(${pr},${pg},${pb},0.60)`;
        const previewBrushFill = `rgba(${pr},${pg},${pb},0.08)`;
        const previewBrushStroke = `rgba(${pr},${pg},${pb},0.78)`;
        const previewBrushPath = `rgba(${pr},${pg},${pb},0.24)`;
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
            octx.strokeStyle = previewStroke;
            octx.lineWidth = 2;
            octx.setLineDash([6, 3]);
            octx.stroke();
            octx.setLineDash([]);

            // text text
            octx.beginPath();
            octx.arc(cx0, cy0, 6, 0, Math.PI * 2);
            octx.fillStyle = previewFillStrong;
            octx.fill();
            octx.strokeStyle = '#fff';
            octx.lineWidth = 1;
            octx.stroke();

            // text text
            for (const [sx, sy] of this._drawingPoints) {
                const [cx, cy] = this.sceneToCanvas(sx, sy);
                octx.beginPath();
                octx.arc(cx, cy, 3, 0, Math.PI * 2);
                octx.fillStyle = previewStrokeStrong;
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
                octx.strokeStyle = previewBrushPath;
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
                octx.fillStyle = previewBrushFill;
                octx.fill();
                octx.strokeStyle = previewBrushStroke;
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
            octx.fillStyle = previewFill;
            octx.fillRect(x, y, w, h);
            octx.strokeStyle = previewStroke;
            octx.lineWidth = 2;
            octx.setLineDash([6, 3]);
            octx.strokeRect(x, y, w, h);
            octx.setLineDash([]);
        }

        // Ruler — text text text. annotation text text drawMode text text text.
        if (this.drawMode === 'ruler' && this._rulerStart && this._rulerEnd) {
            this._renderRulerPreview(octx);
        }

        // 1mm² text text text — text text text text.
        if ((this.drawMode === 'rect-1mm2' || this.drawMode === 'circle-1mm2')
                && this._drawingCurrent) {
            const [sx, sy] = this._drawingCurrent;
            const coords = this.drawMode === 'rect-1mm2'
                ? this._makeRect1mm2Coords(sx, sy)
                : this._makeCircle1mm2Coords(sx, sy);
            if (coords) {
                const fillColor = previewFill;
                const strokeColor = previewStrokeStrong;
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
                // text text
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

    /** text text text annotationtext text text text */
    _getEditableSelectedPolygon() {
        const ann = this.annotations.find(a => a.id === this.selectedAnnotationId);
        if (!ann || !ann.visible || this._isAnnotationClassHidden(ann)) return null;
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
            if (!ann || !ann.visible || this._isAnnotationClassHidden(ann) || ann.type !== 'polygon' || !Array.isArray(ann.coordinates) || ann.coordinates.length < 3) {
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
        if (!sel || !sel.visible || this._isAnnotationClassHidden(sel)) return null;
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

    /** scene text annotation text text (text: text text text text) */
    _hitAnnotation(sx, sy) {
        const threshold = Math.max(4, 8 / Math.max(this.zoom, 0.0001));
        for (let i = this.annotations.length - 1; i >= 0; i--) {
            const ann = this.annotations[i];
            if (!ann.visible) continue;
            if (this._isAnnotationClassHidden(ann)) continue;

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
            if (this._isAnnotationClassHidden(ann)) continue;
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

    /** annotation text text text */
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

    // ── text ──

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
