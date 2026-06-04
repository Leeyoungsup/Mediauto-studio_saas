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
        this.viewerSynced = false;
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

    async open(slideId, patch, options = {}) {
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
        if (options.syncViewer !== false) this.syncViewer();
        else this.viewerSynced = false;
        this.viewer.requestRender();
        this.render();
    }

    _patchBounds() {
        const patch = this.patch || {};
        const x = Number(patch.x ?? patch.int_x ?? 0);
        const y = Number(patch.y ?? patch.int_y ?? 0);
        const w = Number(patch.w ?? patch.int_w ?? patch.width ?? 0);
        const h = Number(patch.h ?? patch.int_h ?? patch.height ?? 0);
        return { x, y, w, h };
    }

    _annotationPoints(annotation) {
        const candidates = [
            annotation?.coordinates,
            annotation?.points,
            annotation?.list_points,
            annotation?.properties?.coordinates,
            annotation?.properties?.points,
        ];
        for (const value of candidates) {
            if (!Array.isArray(value)) continue;
            const points = value
                .map((point) => {
                    if (Array.isArray(point) && point.length >= 2) return [Number(point[0]), Number(point[1])];
                    if (point && typeof point === 'object') return [Number(point.x), Number(point.y)];
                    return null;
                })
                .filter((point) => Number.isFinite(point?.[0]) && Number.isFinite(point?.[1]));
            if (points.length) return points;
        }
        const x = Number(annotation?.x ?? annotation?.slide_x);
        const y = Number(annotation?.y ?? annotation?.slide_y);
        return Number.isFinite(x) && Number.isFinite(y) ? [[x, y]] : [];
    }

    _annotationLabelClass(annotation) {
        const classId = annotation?.class_id ?? annotation?.classId ?? annotation?.properties?.class_id ?? annotation?.properties?.classId ?? '';
        const className = annotation?.class_name ?? annotation?.className ?? annotation?.properties?.class_name ?? annotation?.properties?.className ?? '';
        return { class_id: String(classId || ''), class_name: String(className || '') };
    }

    _status() {
        return String(this.patch?.str_status || this.patch?.status || 'required').toLowerCase();
    }

    _annotationStatus() {
        const explicit = String(this.patch?.str_annotation_status || this.patch?.annotation_status || '').toLowerCase();
        if (explicit) return explicit;
        const status = this._status();
        if (['required', 'in_progress', 'completed', 'not_required'].includes(status)) return status;
        if (['reviewed', 'rejected'].includes(status)) return 'completed';
        return 'required';
    }

    _draftSaveOptions(complete) {
        const options = { complete };
        if (complete) return options;
        const annotationStatus = this._annotationStatus();
        if (['required', 'in_progress'].includes(annotationStatus)) {
            options.status = annotationStatus;
            options.annotation_status = annotationStatus;
            options.preserve_status = true;
        }
        return options;
    }

    _cellToAnnotation(cell, idx = 0) {
        const coords = Array.isArray(cell?.coordinates) && cell.coordinates.length
            ? cell.coordinates
            : (Array.isArray(cell?.local_coordinates) ? cell.local_coordinates.map(([x, y]) => {
                const patch = this._patchBounds();
                return [Number(x) + patch.x, Number(y) + patch.y];
            }) : []);
        let coordinates = coords
            .map(point => Array.isArray(point) ? [Number(point[0]), Number(point[1])] : [Number(point.x), Number(point.y)])
            .filter(point => Number.isFinite(point[0]) && Number.isFinite(point[1]));
        if (!coordinates.length && cell?.bbox) {
            const x = Number(cell.bbox.x ?? cell.bbox.x0);
            const y = Number(cell.bbox.y ?? cell.bbox.y0);
            const w = Math.max(1, Number(cell.bbox.width ?? (Number(cell.bbox.x1) - x)));
            const h = Math.max(1, Number(cell.bbox.height ?? (Number(cell.bbox.y1) - y)));
            if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(w) && Number.isFinite(h)) {
                coordinates = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
            }
        }
        const classId = String(cell?.class_id ?? cell?.classId ?? '');
        const className = String(cell?.class_name ?? cell?.className ?? '');
        const color = cell?.color || cell?.class_color || cell?.properties?.color || [0, 255, 0];
        return {
            id: String(cell?.id || `patch_cell_${idx + 1}`),
            name: String(idx + 1),
            type: String(cell?.shape_type || cell?.type || 'rectangle'),
            coordinates,
            color,
            visible: cell?.visible !== false,
            selected: false,
            class_id: classId,
            class_name: className,
            source: cell?.source || 'patch_cell_annotation',
            properties: {
                ...(cell?.properties || {}),
                class_id: classId,
                class_name: className,
                source: cell?.source || 'patch_cell_annotation',
            },
        };
    }

    _annotationToPatchCell(annotation) {
        const points = this._annotationPoints(annotation);
        if (!points.length) throw new Error('Annotation has no slide coordinates.');
        const xs = points.map(point => point[0]);
        const ys = points.map(point => point[1]);
        const x0 = Math.min(...xs);
        const y0 = Math.min(...ys);
        const x1 = Math.max(...xs);
        const y1 = Math.max(...ys);
        const centerX = Number.isFinite(Number(annotation?.x)) ? Number(annotation.x) : (x0 + x1) / 2;
        const centerY = Number.isFinite(Number(annotation?.y)) ? Number(annotation.y) : (y0 + y1) / 2;
        const patch = this._patchBounds();
        const labelClass = this._annotationLabelClass(annotation);
        const localPoints = points.map(([x, y]) => [x - patch.x, y - patch.y]);
        const type = String(annotation?.type || annotation?.shape_type || annotation?.tool || 'polygon');
        return {
            id: String(annotation?.id || `cell_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`),
            type,
            shape_type: type,
            x: centerX,
            y: centerY,
            local_x: centerX - patch.x,
            local_y: centerY - patch.y,
            coordinates: points,
            local_coordinates: localPoints,
            bbox: {
                x: x0,
                y: y0,
                width: Math.max(1, x1 - x0),
                height: Math.max(1, y1 - y0),
                x0,
                y0,
                x1,
                y1,
            },
            class_id: labelClass.class_id,
            class_name: labelClass.class_name,
            color: Array.isArray(annotation?.color) ? annotation.color.slice(0, 3) : annotation?.color,
            confidence: Number(annotation?.confidence ?? 1),
            source: 'manual_patch_annotation',
        };
    }

    syncViewer() {
        if (!this.viewer || !this.patch) return;
        this.viewer.setDetectionResults?.([]);
        this.viewer.annotations = (this.cells || []).map((cell, idx) => this._cellToAnnotation(cell, idx));
        this.viewer.selectedAnnotationId = null;
        this.viewer._annotationCounter = this.viewer.annotations.length;
        this.viewerSynced = true;
        this.viewer.requestRender?.();
    }

    async addAnnotationLabel(annotation) {
        if (!this.slideId || !this.patch) throw new Error('No patch is selected.');
        const cell = this._annotationToPatchCell(annotation);
        this.cells = [...(this.cells || []), cell];
        this.viewer?.requestRender?.();
        this.onStatus(`Patch label added: ${this.patch.patch_id}`);
        this.render();
        return cell;
    }

    clearViewerAnnotations() {
        if (!this.viewerSynced || !this.viewer) return;
        this.viewer.annotations = [];
        this.viewer.selectedAnnotationId = null;
        this.viewer._annotationCounter = 0;
        this.viewerSynced = false;
        this.viewer.requestRender?.();
    }

    close() {
        this.clearViewerAnnotations();
        this.patch = null;
        this.cells = [];
        this.viewerSynced = false;
        this.statusLayer?.setSelectedPatch('');
        this.viewer?.requestRender();
        this.render();
    }

    async save({ complete = false } = {}) {
        if (!this.slideId || !this.patch) return;
        const patch = this._patchBounds();
        const cells = this.viewerSynced
            ? (this.viewer?.annotations || []).map((ann, idx) => ({
                ...this._annotationToPatchCell(ann),
                id: ann.id || `cell_${idx + 1}`,
            }))
            : (this.cells || []).map((cell, idx) => ({
                ...cell,
                id: cell.id || `cell_${idx + 1}`,
                x: Number(cell.x),
                y: Number(cell.y),
                local_x: Number.isFinite(Number(cell.local_x)) ? Number(cell.local_x) : Number(cell.x) - patch.x,
                local_y: Number.isFinite(Number(cell.local_y)) ? Number(cell.local_y) : Number(cell.y) - patch.y,
            }));
        const result = await this.api.savePatchCells(
            this.slideId,
            this.patch.patch_id,
            cells,
            this._draftSaveOptions(complete),
        );
        this.cells = cells;
        const resultPatch = complete ? (result.patch || {}) : {};
        const annotationStatus = this._annotationStatus();
        this.patch = {
            ...this.patch,
            ...resultPatch,
            patch_id: this.patch.patch_id,
            str_status: complete
                ? (result.patch_status || result.patch?.str_status || 'completed')
                : (this.patch.str_status || annotationStatus || 'in_progress'),
            str_annotation_status: complete
                ? (result.patch?.str_annotation_status || 'completed')
                : (this.patch.str_annotation_status || annotationStatus || 'in_progress'),
            str_review_status: complete
                ? (result.patch?.str_review_status || this.patch.str_review_status || 'pending')
                : (this.patch.str_review_status || 'pending'),
            str_termination_status: complete
                ? (result.patch?.str_termination_status || this.patch.str_termination_status || 'pending')
                : (this.patch.str_termination_status || 'pending'),
        };
        this.onSaved(this.patch);
        this.onStatus(`${complete ? 'Patch saved complete' : 'Patch saved'}: ${this.patch.patch_id}`);
        this.render();
        return this.patch;
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
        const annotationStatus = this._annotationStatus();
        const canSaveDraft = annotationStatus === 'in_progress';
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
                <button type="button" data-action="save" ${canSaveDraft ? '' : 'disabled'}>Save</button>
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
