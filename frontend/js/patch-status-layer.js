const STATUS_STYLE = {
    not_required: { fill: '148, 163, 184', stroke: 'rgba(148, 163, 184, 0.35)' },
    required: { fill: '245, 158, 11', stroke: 'rgba(245, 158, 11, 0.85)' },
    pending_required: { fill: '245, 158, 11', stroke: 'rgba(245, 158, 11, 0.95)' },
    pending_excluded: { fill: '239, 68, 68', stroke: 'rgba(239, 68, 68, 0.95)' },
    in_progress: { fill: '59, 130, 246', stroke: 'rgba(59, 130, 246, 0.85)' },
    completed: { fill: '34, 197, 94', stroke: 'rgba(34, 197, 94, 0.85)' },
    reviewed: { fill: '16, 185, 129', stroke: 'rgba(16, 185, 129, 0.95)' },
    rejected: { fill: '239, 68, 68', stroke: 'rgba(239, 68, 68, 0.85)' },
};

export class PatchStatusLayer {
    constructor(options = {}) {
        this.patches = new Map();
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
        ctx.save();
        this._drawPatches(ctx, viewer, this.pendingPatches, true);
        this._drawPatches(ctx, viewer, this.patches.values(), false);
        ctx.restore();
    }

    _drawPatches(ctx, viewer, patches, pending) {
        for (const patch of patches) {
            const status = patch.str_status || patch.status || 'required';
            if (status === 'not_required') continue;
            const x = Number(patch.int_x ?? patch.x ?? 0);
            const y = Number(patch.int_y ?? patch.y ?? 0);
            const w = Number(patch.int_w ?? patch.w ?? 0);
            const h = Number(patch.int_h ?? patch.h ?? 0);
            if (w <= 0 || h <= 0) continue;
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
}
