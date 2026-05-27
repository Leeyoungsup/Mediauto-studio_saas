import { PatchGridLayer } from './patch-grid-layer.js?v=20260527-07';
import { PatchStatusLayer } from './patch-status-layer.js?v=20260527-02';
import { WsiRequiredRegionLayer } from './wsi-required-region-layer.js?v=20260526-06';
import { CellAnnotationEditor } from './cell-annotation-editor.js?v=20260526-06';

class PatchFocusLayer {
    constructor() {
        this.patch = null;
        this.visible = false;
    }

    setPatch(patch) {
        this.patch = patch || null;
        this.visible = Boolean(patch);
    }

    clear() {
        this.patch = null;
        this.visible = false;
    }

    draw(ctx, viewer) {
        if (!this.visible || !this.patch || !viewer?.slideInfo) return;
        const x = Number(this.patch.x ?? this.patch.int_x ?? 0);
        const y = Number(this.patch.y ?? this.patch.int_y ?? 0);
        const w = Number(this.patch.w ?? this.patch.int_w ?? 0);
        const h = Number(this.patch.h ?? this.patch.int_h ?? 0);
        if (w <= 0 || h <= 0) return;
        const [cx, cy] = viewer.sceneToCanvas(x, y);
        const cw = w * viewer.zoom;
        const ch = h * viewer.zoom;
        ctx.save();
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.rect(0, 0, viewer._viewW, viewer._viewH);
        ctx.rect(cx, cy, cw, ch);
        ctx.fill('evenodd');
        ctx.strokeStyle = '#6c5ce7';
        ctx.lineWidth = 2;
        ctx.strokeRect(cx, cy, cw, ch);
        ctx.restore();
    }
}

export class CellPatchWorkflow {
    constructor({ api, viewer, canvas, setStatus, onRequiredRegionSaved } = {}) {
        this.api = api;
        this.viewer = viewer;
        this.canvas = canvas;
        this.setStatus = setStatus || (() => {});
        this.onRequiredRegionSaved = onRequiredRegionSaved || (() => {});
        this.slideId = '';
        this.grid = new PatchGridLayer();
        this.status = new PatchStatusLayer();
        this.required = new WsiRequiredRegionLayer({ visible: false });
        this.focusLayer = new PatchFocusLayer();
        this.patches = new Map();
        this.patchListEl = document.getElementById('annotation-list');
        this.patchHeaderEl = document.querySelector('.annotation-group > .panel-header');
        this.lastRegionAction = null;
        this.selectedPatch = null;
        this.patchFocusActive = false;
        this.savedWsiView = null;
        this.lastWsiViewBeforePatchOpen = null;
        this.layerVisibilityBeforePatchView = null;
        this.toolbarToggle = null;
        this.editor = new CellAnnotationEditor({
            api,
            viewer,
            statusLayer: this.status,
            onStatus: this.setStatus,
            onSaved: (patch) => this.updatePatch(patch),
        });
        this._setupRightPanel();
        this._setupToolbarToggle();
        this.viewer.addOverlayLayer(this.required);
        this.viewer.addOverlayLayer(this.status);
        this.viewer.addOverlayLayer(this.grid);
        this.viewer.addOverlayLayer(this.focusLayer);
        this._bindEvents();
    }

    _setupRightPanel() {
        document.body.classList.add('cell-patch-workflow-page');
        if (this.patchHeaderEl) this.patchHeaderEl.textContent = 'Required Patches';
        this.renderPatchList();
    }

    _setupToolbarToggle() {
        const toolbar = document.getElementById('toolbar') || document.querySelector('.viewer-toolbar, #viewer-toolbar, nav.toolbar');
        if (!toolbar || document.getElementById('cell-patch-view-toggle')) return;
        const btn = document.createElement('button');
        btn.id = 'cell-patch-view-toggle';
        btn.type = 'button';
        btn.className = 'toolbar-btn patch-view-toolbar-toggle';
        btn.title = 'Toggle selected patch view (P)';
        btn.textContent = 'Patch View';
        btn.disabled = true;
        btn.addEventListener('click', () => this.togglePatchView());
        const spacer = toolbar.querySelector('.toolbar-spacer');
        toolbar.insertBefore(btn, spacer || null);
        this.toolbarToggle = btn;
        this._syncToolbarToggle();
    }

    _syncToolbarToggle() {
        if (!this.toolbarToggle) return;
        this.toolbarToggle.disabled = !this.selectedPatch;
        this.toolbarToggle.textContent = this.patchFocusActive ? 'WSI View' : 'Patch View';
        this.toolbarToggle.classList.toggle('active', this.patchFocusActive);
    }

    _bindEvents() {
        this.canvas?.addEventListener('click', (e) => {
            if (this.patchFocusActive) {
                e.preventDefault();
                e.stopImmediatePropagation?.();
                e.stopPropagation();
                return;
            }
            if (!this.slideId || this.viewer.drawMode) return;
            const rect = this.canvas.getBoundingClientRect();
            const [sx, sy] = this.viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
            const patch = this.grid.patchAt(sx, sy);
            if (!patch) return;
            const saved = this._findPatchRecord(patch);
            if (!saved || (saved.str_status || saved.status) === 'not_required') return;
            this.openPatch({ ...patch, ...saved });
            this.renderPatchList();
        }, true);

        this.canvas?.addEventListener('dblclick', (e) => {
            if (this.patchFocusActive) {
                e.preventDefault();
                e.stopImmediatePropagation?.();
                e.stopPropagation();
                return;
            }
            if (!this.slideId || this.viewer.drawMode) return;
            const rect = this.canvas.getBoundingClientRect();
            const [sx, sy] = this.viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
            const patch = this.grid.patchAt(sx, sy);
            const saved = patch ? this._findPatchRecord(patch) : null;
            if (!patch || !saved || (saved.str_status || saved.status) === 'not_required') return;
            this.openPatch({ ...patch, ...saved }).then(() => this.enterPatchView());
            e.preventDefault();
            e.stopPropagation();
        }, true);

        window.addEventListener('keydown', (e) => {
            const tag = (e.target && e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;
            if (String(e.key || '').toLowerCase() !== 'p') return;
            if (!this.selectedPatch) return;
            this.togglePatchView();
            e.preventDefault();
        }, true);
    }

    async load(slideId) {
        this.slideId = slideId || '';
        this.patches.clear();
        this.exitPatchView({ restore: false });
        this.selectedPatch = null;
        this.lastWsiViewBeforePatchOpen = null;
        this._syncToolbarToggle();
        this.editor.close();
        this.renderPatchList();
        if (!this.slideId) return;
        const config = await this.api.getCellGridConfig(slideId);
        this.grid.setConfig(config);
        const regionPayload = await this.api.getCellRequiredRegions(slideId);
        this.required.setRegions(regionPayload.regions || []);
        await this.refreshPatches();
        this.viewer.requestRender();
    }

    async refreshPatches() {
        if (!this.slideId) return;
        const payload = await this.api.getCellPatches(this.slideId);
        this.patches.clear();
        for (const patch of payload.patches || []) {
            const id = patch.str_patch_id || patch.patch_id;
            if (id && this._patchMatchesCurrentGrid(patch)) {
                this.patches.set(id, { ...patch, patch_id: id });
            }
        }
        this.status.setPatches(Array.from(this.patches.values()));
        this.renderPatchList();
        this.viewer.requestRender();
    }

    updatePatch(patch) {
        const id = patch.str_patch_id || patch.patch_id;
        if (!id) return;
        if (!this._patchMatchesCurrentGrid(patch)) return;
        this.patches.set(id, { ...patch, patch_id: id });
        this.status.setPatches(Array.from(this.patches.values()));
        this.renderPatchList();
        this.viewer.requestRender();
    }

    _patchMatchesCurrentGrid(patch) {
        const config = this.grid?.config;
        if (!config) return true;
        const size = Number(config.patch_size_slide_px || 0);
        if (size <= 0) return true;
        const px = Number(patch.int_px ?? patch.px);
        const py = Number(patch.int_py ?? patch.py);
        if (!Number.isFinite(px) || !Number.isFinite(py)) return true;
        const expectedX = Math.round(px * size);
        const expectedY = Math.round(py * size);
        const actualX = Math.round(Number(patch.int_x ?? patch.x ?? expectedX));
        const actualY = Math.round(Number(patch.int_y ?? patch.y ?? expectedY));
        return Math.abs(actualX - expectedX) <= 1 && Math.abs(actualY - expectedY) <= 1;
    }

    _findPatchRecord(patch) {
        if (!patch) return null;
        const direct = this.patches.get(patch.patch_id || patch.str_patch_id);
        if (direct) return direct;
        const legacyId = `px_${Number(patch.px ?? patch.int_px ?? 0)}_py_${Number(patch.py ?? patch.int_py ?? 0)}`;
        return this.patches.get(legacyId) || null;
    }

    renderPatchList() {
        if (!this.patchListEl) return;
        const list = Array.from(this.patches.values())
            .filter(patch => (patch.str_status || patch.status || 'not_required') !== 'not_required')
            .sort((a, b) => {
                const ay = Number(a.int_py ?? a.py ?? 0);
                const by = Number(b.int_py ?? b.py ?? 0);
                const ax = Number(a.int_px ?? a.px ?? 0);
                const bx = Number(b.int_px ?? b.px ?? 0);
                return ay - by || ax - bx;
            });
        const statusCounts = list.reduce((acc, patch) => {
            const status = patch.str_status || patch.status || 'required';
            acc[status] = (acc[status] || 0) + 1;
            return acc;
        }, {});
        const countText = Object.entries(statusCounts)
            .map(([status, count]) => `${this._statusLabel(status)} ${count}`)
            .join(' / ');
        this.patchListEl.innerHTML = `
            <div class="patch-list-summary">
                <div>
                    <strong>${list.length}</strong>
                    <span>${list.length === 1 ? 'patch requires labeling' : 'patches require labeling'}</span>
                </div>
                <button type="button" class="patch-region-undo" ${this.canUndoRequiredRegion() ? '' : 'disabled'} title="Undo last required region">Undo Region</button>
            </div>
            ${countText ? `<div class="patch-list-counts">${this._escape(countText)}</div>` : ''}
        `;
        this.patchListEl.querySelector('.patch-region-undo')?.addEventListener('click', () => {
            this.undoLastRequiredRegion().catch((err) => {
                this.setStatus(`Required region undo failed: ${err.message}`);
            });
        });
        if (!this.slideId) {
            this.patchListEl.insertAdjacentHTML('beforeend', '<div class="patch-list-empty">Open a slide to load required patches.</div>');
            return;
        }
        if (!list.length) {
            this.patchListEl.insertAdjacentHTML('beforeend', '<div class="patch-list-empty">No required patches. Draw a required region to create patch tasks.</div>');
            return;
        }
        const body = document.createElement('div');
        body.className = 'patch-task-list';
        const header = document.createElement('div');
        header.className = 'patch-task-header';
        header.innerHTML = `
            <span>Patch</span>
            <span>Annotation</span>
            <span>Review</span>
            <span>Termination</span>
        `;
        body.appendChild(header);
        for (const patch of list) {
            const id = patch.str_patch_id || patch.patch_id;
            const status = patch.str_status || patch.status || 'required';
            const workflow = this._patchWorkflowStatus(patch);
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'patch-task-row';
            row.dataset.patchId = id;
            row.dataset.status = status;
            if (id && id === this.selectedPatchId()) row.classList.add('selected');
            row.innerHTML = `
                <span class="patch-task-main">
                    <span class="patch-task-id">${this._escape(id)}</span>
                    <span class="patch-task-coord">X ${Number(patch.int_x ?? patch.x ?? 0).toLocaleString()} / Y ${Number(patch.int_y ?? patch.y ?? 0).toLocaleString()}</span>
                </span>
                <span class="patch-task-step" data-step-status="${this._escape(workflow.annotation)}">${this._escape(this._workflowLabel(workflow.annotation))}</span>
                <span class="patch-task-step" data-step-status="${this._escape(workflow.review)}">${this._escape(this._workflowLabel(workflow.review))}</span>
                <span class="patch-task-step" data-step-status="${this._escape(workflow.termination)}">${this._escape(this._workflowLabel(workflow.termination))}</span>
            `;
            row.addEventListener('click', () => this.openPatchFromList(id));
            row.addEventListener('dblclick', (event) => {
                this.openPatchFromList(id).then(() => this.enterPatchView());
                event.preventDefault();
            });
            body.appendChild(row);
        }
        this.patchListEl.appendChild(body);
    }

    _patchWorkflowStatus(patch) {
        const status = patch.str_status || patch.status || 'required';
        return {
            annotation: patch.str_annotation_status || this._derivedWorkflowStatus(status, 'annotation'),
            review: patch.str_review_status || this._derivedWorkflowStatus(status, 'review'),
            termination: patch.str_termination_status || this._derivedWorkflowStatus(status, 'termination'),
        };
    }

    _derivedWorkflowStatus(status, step) {
        if (step === 'annotation') {
            if (status === 'required') return 'required';
            if (status === 'in_progress') return 'in_progress';
            if (status === 'not_required') return 'not_required';
            return 'completed';
        }
        if (step === 'review') {
            if (status === 'reviewed') return 'reviewed';
            if (status === 'rejected') return 'rejected';
            if (status === 'completed') return 'current';
            return 'pending';
        }
        if (step === 'termination') {
            if (status === 'reviewed' || status === 'rejected') return 'current';
            return 'pending';
        }
        return 'pending';
    }

    _workflowLabel(status) {
        return {
            required: 'Required',
            in_progress: 'Running',
            completed: 'Done',
            reviewed: 'Done',
            rejected: 'Rejected',
            current: 'Current',
            pending: '-',
            not_required: '-',
        }[status] || '-';
    }

    async openPatchFromList(patchId) {
        if (!patchId || !this.slideId) return;
        const saved = this.patches.get(patchId);
        if (!saved) return;
        const patch = this.grid.patchAt(Number(saved.int_x ?? saved.x ?? 0) + 1, Number(saved.int_y ?? saved.y ?? 0) + 1);
        await this.openPatch({
            ...(patch || {}),
            ...saved,
            patch_id: patchId,
            x: Number(saved.int_x ?? saved.x ?? patch?.x ?? 0),
            y: Number(saved.int_y ?? saved.y ?? patch?.y ?? 0),
            w: Number(saved.int_w ?? saved.w ?? patch?.w ?? 0),
            h: Number(saved.int_h ?? saved.h ?? patch?.h ?? 0),
        });
        this.renderPatchList();
    }

    async openPatch(patch) {
        if (!patch || !this.slideId) return;
        if (!this.patchFocusActive && !this.lastWsiViewBeforePatchOpen) {
            this.lastWsiViewBeforePatchOpen = {
                viewCenterX: this.viewer.viewCenterX,
                viewCenterY: this.viewer.viewCenterY,
                zoom: this.viewer.zoom,
            };
        }
        this.selectedPatch = this._normalizePatchView(patch);
        await this.editor.open(this.slideId, this.selectedPatch);
        if (this.patchFocusActive) this.focusLayer.setPatch(this.selectedPatch);
        this.renderPatchList();
        this._syncToolbarToggle();
    }

    selectedPatchId() {
        return this.selectedPatch?.patch_id || this.selectedPatch?.str_patch_id || this.status.selectedPatchId || '';
    }

    _normalizePatchView(patch) {
        return {
            ...patch,
            patch_id: patch.patch_id || patch.str_patch_id,
            x: Number(patch.x ?? patch.int_x ?? 0),
            y: Number(patch.y ?? patch.int_y ?? 0),
            w: Number(patch.w ?? patch.int_w ?? 0),
            h: Number(patch.h ?? patch.int_h ?? 0),
        };
    }

    _fitPatchView(patch) {
        if (!patch || !this.viewer) return;
        const w = Number(patch.w || 0);
        const h = Number(patch.h || 0);
        if (w <= 0 || h <= 0) return;
        this.viewer.viewCenterX = Number(patch.x || 0) + w / 2;
        this.viewer.viewCenterY = Number(patch.y || 0) + h / 2;
        const fitZoom = Math.min(this.viewer._viewW / w, this.viewer._viewH / h) * 0.98;
        this.viewer.setZoom(Math.max(this.viewer.minZoom, Math.min(this.viewer.maxZoom, fitZoom)));
        this.viewer.requestRender();
        this.viewer.onViewChange?.();
    }

    enterPatchView() {
        if (!this.selectedPatch || this.patchFocusActive) return;
        this.savedWsiView = this.lastWsiViewBeforePatchOpen || {
            viewCenterX: this.viewer.viewCenterX,
            viewCenterY: this.viewer.viewCenterY,
            zoom: this.viewer.zoom,
        };
        this.patchFocusActive = true;
        this.layerVisibilityBeforePatchView = {
            required: this.required.visible,
            status: this.status.visible,
            grid: this.grid.visible,
        };
        this.required.visible = false;
        this.status.visible = false;
        this.grid.visible = false;
        this.viewer.setViewBounds?.(this.selectedPatch);
        this.focusLayer.setPatch(this.selectedPatch);
        this._fitPatchView(this.selectedPatch);
        this.renderPatchList();
        this._syncToolbarToggle();
        this.setStatus(`Patch view: ${this.selectedPatch.patch_id}`);
    }

    exitPatchView({ restore = true } = {}) {
        if (!this.patchFocusActive && !this.focusLayer.visible) return;
        this.patchFocusActive = false;
        this.focusLayer.clear();
        if (this.layerVisibilityBeforePatchView) {
            this.required.visible = this.layerVisibilityBeforePatchView.required;
            this.status.visible = this.layerVisibilityBeforePatchView.status;
            this.grid.visible = this.layerVisibilityBeforePatchView.grid;
        }
        this.viewer.setViewBounds?.(null);
        if (restore && this.savedWsiView) {
            this.viewer.viewCenterX = this.savedWsiView.viewCenterX;
            this.viewer.viewCenterY = this.savedWsiView.viewCenterY;
            this.viewer.zoom = this.savedWsiView.zoom;
            this.viewer._clampView?.();
            this.viewer._emitZoomChange?.();
        }
        this.savedWsiView = null;
        this.lastWsiViewBeforePatchOpen = null;
        this.layerVisibilityBeforePatchView = null;
        this.viewer.requestRender();
        this.renderPatchList();
        this._syncToolbarToggle();
        this.setStatus('WSI view restored');
    }

    togglePatchView() {
        if (this.patchFocusActive) {
            this.exitPatchView();
        } else {
            this.enterPatchView();
        }
    }

    _statusLabel(status) {
        return {
            required: 'Required',
            in_progress: 'In Progress',
            completed: 'Completed',
            reviewed: 'Reviewed',
            rejected: 'Rejected',
            not_required: 'Not Required',
        }[status] || 'Required';
    }

    _escape(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    canUndoRequiredRegion() {
        return Boolean(this.slideId && this.required.toApiRegions().length);
    }

    async undoLastRequiredRegion() {
        if (!this.canUndoRequiredRegion()) return false;
        const regions = this.required.toApiRegions();
        const targetId = this.lastRegionAction?.regionId;
        let nextRegions = regions;
        if (targetId) {
            const idx = regions.findIndex(region => region.id === targetId);
            if (idx >= 0) nextRegions = regions.filter((_, regionIdx) => regionIdx !== idx);
        }
        if (nextRegions === regions) nextRegions = regions.slice(0, -1);
        await this.api.saveCellRequiredRegions(this.slideId, nextRegions);
        await this.api.recomputeCellPatchStatus(this.slideId);
        const regionPayload = await this.api.getCellRequiredRegions(this.slideId);
        this.required.setRegions(regionPayload.regions || []);
        this.lastRegionAction = null;
        await this.refreshPatches();
        this.setStatus('Required region undone and patch status recomputed');
        this.viewer?.requestRender?.();
        return true;
    }

    async addRequiredRegionFromAnnotation(annotation) {
        if (!this.slideId || !annotation) return;
        const coords = annotation.coordinates || [];
        if (coords.length < 3) return;
        const regions = this.required.toApiRegions();
        const regionId = `region_${Date.now()}`;
        regions.push({
            id: regionId,
            type: 'annotation_required_region',
            points: coords.map(pt => [Number(pt[0]), Number(pt[1])]),
        });
        await this.api.saveCellRequiredRegions(this.slideId, regions);
        await this.api.recomputeCellPatchStatus(this.slideId);
        const regionPayload = await this.api.getCellRequiredRegions(this.slideId);
        this.required.setRegions(regionPayload.regions || []);
        this.lastRegionAction = { regionId };
        await this.refreshPatches();
        await this.onRequiredRegionSaved({ regionId });
        this.setStatus('Required region saved and patch status recomputed');
    }
}
