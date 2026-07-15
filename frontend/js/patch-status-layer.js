const STATUS_STYLE = {
    not_required: { fill: '148, 163, 184', stroke: 'rgba(148, 163, 184, 0.35)' },
    required: { fill: '245, 158, 11', stroke: 'rgba(217, 119, 6, 0.9)' },
    pending_required: { fill: '34, 197, 94', stroke: 'rgba(34, 197, 94, 0.98)' },
    pending_excluded: { fill: '239, 68, 68', stroke: 'rgba(239, 68, 68, 0.95)' },
    in_progress: { fill: '245, 158, 11', stroke: 'rgba(245, 158, 11, 0.95)' },
    completed: { fill: '34, 197, 94', stroke: 'rgba(34, 197, 94, 0.85)' },
    current: { fill: '59, 130, 246', stroke: 'rgba(59, 130, 246, 0.95)' },
    reviewed: { fill: '59, 130, 246', stroke: 'rgba(59, 130, 246, 0.95)' },
    rejected: { fill: '239, 68, 68', stroke: 'rgba(239, 68, 68, 0.85)' },
    termination_current: { fill: '139, 92, 246', stroke: 'rgba(139, 92, 246, 0.9)' },
    terminated: { fill: '100, 116, 139', stroke: 'rgba(100, 116, 139, 0.9)' },
};

export class PatchStatusLayer {
    constructor(options = {}) {
        this.patches = new Map();
        this.patchList = [];
        this.visible = options.visible !== false;
        this.minScreenSize = options.minScreenSize || 10;
        this.selectedPatchId = '';
        this.fillOpacity = Number(options.fillOpacity ?? 0.05);
        this.strokeWidth = Number(options.strokeWidth ?? 1);
        this.pendingPatches = [];
    }

    setPatches(patches = []) {
        this.patches.clear();
        for (const patch of patches || []) {
            const id = patch.str_patch_id || patch.patch_id;
            if (id) this.patches.set(id, patch);
        }
        this.patchList = Array.from(this.patches.values()).sort((a, b) => {
            const ay = Number(a.int_y ?? a.y ?? 0);
            const by = Number(b.int_y ?? b.y ?? 0);
            return ay - by || Number(a.int_x ?? a.x ?? 0) - Number(b.int_x ?? b.x ?? 0);
        });
    }

    setSelectedPatch(patchId) {
        this.selectedPatchId = patchId || '';
    }

    setPendingPatches(patches = []) {
        this.pendingPatches = Array.isArray(patches) ? patches : [];
    }

    setStyle(options = {}) {
        if (options.fillOpacity !== undefined) {
            this.fillOpacity = Math.max(0, Math.min(1, Number(options.fillOpacity)));
        }
        if (options.strokeWidth !== undefined) {
            this.strokeWidth = Math.max(0.5, Math.min(8, Number(options.strokeWidth)));
        }
    }

    draw(ctx, viewer) {
        if (!this.visible || !viewer?.slideInfo) return;
        const [sx0, sy0] = viewer.canvasToScene(0, 0);
        const [sx1, sy1] = viewer.canvasToScene(viewer._viewW, viewer._viewH);
        const viewport = {
            x0: Math.min(sx0, sx1),
            y0: Math.min(sy0, sy1),
            x1: Math.max(sx0, sx1),
            y1: Math.max(sy0, sy1),
        };
        ctx.save();
        this._drawPatches(ctx, viewer, this.pendingPatches, true, viewport);
        this._drawPatches(ctx, viewer, this.patchList, false, viewport);
        ctx.restore();
    }

    _drawPatches(ctx, viewer, patches, pending, viewport) {
        for (const patch of patches) {
            const status = pending ? (patch.str_status || patch.status || 'required') : this._displayStatus(patch);
            if (status === 'not_required' || status === 'pending') continue;
            const x = Number(patch.int_x ?? patch.x ?? 0);
            const y = Number(patch.int_y ?? patch.y ?? 0);
            const w = Number(patch.int_w ?? patch.w ?? 0);
            const h = Number(patch.int_h ?? patch.h ?? 0);
            if (w <= 0 || h <= 0) continue;
            if (viewport) {
                if (y > viewport.y1) {
                    if (!pending) break;
                    continue;
                }
                if (y + h < viewport.y0 || x > viewport.x1 || x + w < viewport.x0) continue;
            }
            const [cx, cy] = viewer.sceneToCanvas(x, y);
            const cw = w * viewer.zoom;
            const ch = h * viewer.zoom;
            if (cx > viewer._viewW || cy > viewer._viewH || cx + cw < 0 || cy + ch < 0) continue;
            if (Math.max(cw, ch) < this.minScreenSize) continue;
            const style = STATUS_STYLE[status] || STATUS_STYLE.required;
            ctx.fillStyle = `rgba(${style.fill}, ${this.fillOpacity})`;
            ctx.strokeStyle = (patch.str_patch_id || patch.patch_id) === this.selectedPatchId ? '#2563eb' : style.stroke;
            ctx.lineWidth = (patch.str_patch_id || patch.patch_id) === this.selectedPatchId
                ? Math.max(3, this.strokeWidth + 1.5)
                : this.strokeWidth;
            if (pending) ctx.setLineDash([6, 4]);
            else ctx.setLineDash([]);
            ctx.fillRect(cx, cy, cw, ch);
            ctx.strokeRect(cx, cy, cw, ch);
        }
        ctx.setLineDash([]);
    }

    _displayStatus(patch) {
        const base = String(patch.str_status || patch.status || 'required');
        if (base === 'not_required') return 'not_required';

        const annotation = String(patch.str_annotation_status || patch.annotation_status || '').toLowerCase();
        const review = String(patch.str_review_status || patch.review_status || '').toLowerCase();
        const termination = String(patch.str_termination_status || patch.termination_status || '').toLowerCase();

        if (termination === 'completed') return 'terminated';
        if (termination === 'current' || termination === 'in_progress') return 'termination_current';
        if (review === 'rejected') return 'rejected';
        if (review === 'reviewed') return 'reviewed';
        if (review === 'current' || review === 'in_progress') return 'current';
        if (annotation === 'completed' || base === 'completed') return 'completed';
        if (annotation === 'in_progress' || annotation === 'current' || base === 'in_progress') return 'in_progress';
        if (annotation === 'required' || base === 'required') return 'required';
        return base;
    }
}
