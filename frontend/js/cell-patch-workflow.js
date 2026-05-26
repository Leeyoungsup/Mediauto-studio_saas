import { PatchGridLayer } from './patch-grid-layer.js?v=20260526-06';
import { PatchStatusLayer } from './patch-status-layer.js?v=20260526-06';
import { WsiRequiredRegionLayer } from './wsi-required-region-layer.js?v=20260526-06';
import { CellAnnotationEditor } from './cell-annotation-editor.js?v=20260526-06';

export class CellPatchWorkflow {
    constructor({ api, viewer, canvas, setStatus } = {}) {
        this.api = api;
        this.viewer = viewer;
        this.canvas = canvas;
        this.setStatus = setStatus || (() => {});
        this.slideId = '';
        this.grid = new PatchGridLayer();
        this.status = new PatchStatusLayer();
        this.required = new WsiRequiredRegionLayer();
        this.patches = new Map();
        this.patchListEl = document.getElementById('annotation-list');
        this.patchHeaderEl = document.querySelector('.annotation-group > .panel-header');
        this.lastRegionAction = null;
        this.editor = new CellAnnotationEditor({
            api,
            viewer,
            statusLayer: this.status,
            onStatus: this.setStatus,
            onSaved: (patch) => this.updatePatch(patch),
        });
        this._setupRightPanel();
        this.viewer.addOverlayLayer(this.required);
        this.viewer.addOverlayLayer(this.status);
        this.viewer.addOverlayLayer(this.grid);
        this._bindEvents();
    }

    _setupRightPanel() {
        document.body.classList.add('cell-patch-workflow-page');
        if (this.patchHeaderEl) this.patchHeaderEl.textContent = 'Required Patches';
        this.renderPatchList();
    }

    _bindEvents() {
        this.canvas?.addEventListener('click', (e) => {
            if (!this.slideId || this.viewer.drawMode) return;
            const rect = this.canvas.getBoundingClientRect();
            const [sx, sy] = this.viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
            const patch = this.grid.patchAt(sx, sy);
            if (!patch) return;
            const saved = this.patches.get(patch.patch_id);
            if (!saved || (saved.str_status || saved.status) === 'not_required') return;
            this.editor.open(this.slideId, { ...patch, ...saved });
            this.renderPatchList();
        }, true);
    }

    async load(slideId) {
        this.slideId = slideId || '';
        this.patches.clear();
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
            if (id) this.patches.set(id, { ...patch, patch_id: id });
        }
        this.status.setPatches(Array.from(this.patches.values()));
        this.renderPatchList();
        this.viewer.requestRender();
    }

    updatePatch(patch) {
        const id = patch.str_patch_id || patch.patch_id;
        if (!id) return;
        this.patches.set(id, { ...patch, patch_id: id });
        this.status.setPatches(Array.from(this.patches.values()));
        this.renderPatchList();
        this.viewer.requestRender();
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
        for (const patch of list) {
            const id = patch.str_patch_id || patch.patch_id;
            const status = patch.str_status || patch.status || 'required';
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'patch-task-row';
            row.dataset.patchId = id;
            row.dataset.status = status;
            if (id && id === this.status.selectedPatchId) row.classList.add('selected');
            row.innerHTML = `
                <span class="patch-task-id">${this._escape(id)}</span>
                <span class="patch-task-coord">X${Number(patch.int_px ?? patch.px ?? 0)} Y${Number(patch.int_py ?? patch.py ?? 0)}</span>
                <span class="patch-task-status">${this._escape(this._statusLabel(status))}</span>
            `;
            row.addEventListener('click', () => this.openPatchFromList(id));
            body.appendChild(row);
        }
        this.patchListEl.appendChild(body);
    }

    async openPatchFromList(patchId) {
        if (!patchId || !this.slideId) return;
        const saved = this.patches.get(patchId);
        if (!saved) return;
        const patch = this.grid.patchAt(Number(saved.int_x ?? saved.x ?? 0) + 1, Number(saved.int_y ?? saved.y ?? 0) + 1);
        await this.editor.open(this.slideId, {
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
        this.setStatus('Required region saved and patch status recomputed');
    }
}
