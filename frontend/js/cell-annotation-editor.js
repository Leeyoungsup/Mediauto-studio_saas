export class CellAnnotationEditor {
    constructor({ api, viewer, statusLayer, onStatus, onSaved } = {}) {
        this.api = api;
        this.viewer = viewer;
        this.statusLayer = statusLayer;
        this.onStatus = onStatus || (() => {});
        this.onSaved = onSaved || (() => {});
        this.slideId = '';
        this.patch = null;
        this.cells = [];
        this.panel = null;
        this._ensurePanel();
    }

    _ensurePanel() {
        let panel = document.getElementById('patch-cell-editor');
        if (!panel) {
            panel = document.createElement('section');
            panel.id = 'patch-cell-editor';
            panel.className = 'patch-cell-editor panel-group';
            const right = document.getElementById('right-panel');
            right?.insertBefore(panel, right.querySelector('.results-group'));
        }
        this.panel = panel;
        this.render();
    }

    async open(slideId, patch) {
        this.slideId = slideId;
        this.patch = patch;
        this.statusLayer?.setSelectedPatch(patch?.patch_id || patch?.str_patch_id || '');
        this.viewer?.requestRender();
        this.onStatus(`Patch selected: ${this.patch.patch_id}`);
        try {
            const payload = await this.api.getPatchCells(slideId, this.patch.patch_id);
            this.cells = payload.cells || [];
        } catch (err) {
            this.cells = [];
            this.onStatus(`Patch cells unavailable: ${err.message}`);
        }
        this.viewer?.setDetectionResults?.(this.cells, [[
            [this.patch.x, this.patch.y],
            [this.patch.x + this.patch.w, this.patch.y],
            [this.patch.x + this.patch.w, this.patch.y + this.patch.h],
            [this.patch.x, this.patch.y + this.patch.h],
        ]]);
        this.viewer.viewCenterX = this.patch.x + this.patch.w / 2;
        this.viewer.viewCenterY = this.patch.y + this.patch.h / 2;
        const fitZoom = Math.min(this.viewer._viewW / this.patch.w, this.viewer._viewH / this.patch.h) * 0.9;
        this.viewer.setZoom(Math.max(this.viewer.minZoom, Math.min(this.viewer.maxZoom, fitZoom)));
        this.viewer.requestRender();
        this.render();
    }

    close() {
        this.patch = null;
        this.cells = [];
        this.statusLayer?.setSelectedPatch('');
        this.viewer?.requestRender();
        this.render();
    }

    async save() {
        if (!this.slideId || !this.patch) return;
        const cells = (this.viewer?.detectionCells || this.cells || []).map((cell, idx) => ({
            ...cell,
            id: cell.id || `cell_${idx + 1}`,
            x: Number(cell.x),
            y: Number(cell.y),
            local_x: Number(cell.x) - Number(this.patch.x),
            local_y: Number(cell.y) - Number(this.patch.y),
        }));
        const result = await this.api.savePatchCells(this.slideId, this.patch.patch_id, cells);
        this.cells = cells;
        this.patch.str_status = result.patch_status || 'completed';
        this.onSaved(this.patch);
        this.onStatus(`Patch saved: ${this.patch.patch_id}`);
        this.render();
    }

    async setStatus(status) {
        if (!this.slideId || !this.patch) return;
        const result = await this.api.updatePatchStatus(this.slideId, this.patch.patch_id, status);
        this.patch = { ...this.patch, ...(result.patch || {}), patch_id: this.patch.patch_id };
        this.onSaved(this.patch);
        this.onStatus(`Patch status: ${status}`);
        this.render();
    }

    render() {
        if (!this.panel) return;
        if (!this.patch) {
            this.panel.innerHTML = `
                <div class="panel-header">Patch Cell Annotation</div>
                <div class="patch-editor-empty">Select a required patch on the slide.</div>
            `;
            return;
        }
        const status = this.patch.str_status || this.patch.status || 'required';
        const canReview = window.__currentUserRole === 'admin' || window.__currentUserRole === 'doctor';
        this.panel.innerHTML = `
            <div class="panel-header">Patch Cell Annotation</div>
            <div class="patch-editor-meta">
                <strong>${this.patch.patch_id}</strong>
                <span>${status}</span>
                <span>${this.cells.length} cells</span>
            </div>
            <div class="patch-editor-actions">
                <button type="button" data-action="progress">Start</button>
                <button type="button" data-action="save">Save Complete</button>
                <button type="button" data-action="review" ${canReview ? '' : 'disabled'}>Reviewed</button>
                <button type="button" data-action="reject" ${canReview ? '' : 'disabled'}>Rejected</button>
                <button type="button" data-action="close">Close</button>
            </div>
            <div class="patch-editor-note">
                Cell records are stored with slide x/y and patch-local x/y coordinates.
            </div>
        `;
        this.panel.querySelector('[data-action="progress"]')?.addEventListener('click', () => this.setStatus('in_progress'));
        this.panel.querySelector('[data-action="save"]')?.addEventListener('click', () => this.save());
        this.panel.querySelector('[data-action="review"]')?.addEventListener('click', () => this.setStatus('reviewed'));
        this.panel.querySelector('[data-action="reject"]')?.addEventListener('click', () => this.setStatus('rejected'));
        this.panel.querySelector('[data-action="close"]')?.addEventListener('click', () => this.close());
    }
}
