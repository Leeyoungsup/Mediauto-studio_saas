const STATUS_STYLE = {
    not_required: { fill: 'rgba(148, 163, 184, 0.08)', stroke: 'rgba(148, 163, 184, 0.35)' },
    required: { fill: 'rgba(245, 158, 11, 0.18)', stroke: 'rgba(245, 158, 11, 0.85)' },
    in_progress: { fill: 'rgba(59, 130, 246, 0.18)', stroke: 'rgba(59, 130, 246, 0.85)' },
    completed: { fill: 'rgba(34, 197, 94, 0.16)', stroke: 'rgba(34, 197, 94, 0.85)' },
    reviewed: { fill: 'rgba(16, 185, 129, 0.22)', stroke: 'rgba(16, 185, 129, 0.95)' },
    rejected: { fill: 'rgba(239, 68, 68, 0.18)', stroke: 'rgba(239, 68, 68, 0.85)' },
};

export class PatchStatusLayer {
    constructor(options = {}) {
        this.patches = new Map();
        this.visible = options.visible !== false;
        this.minScreenSize = options.minScreenSize || 10;
        this.selectedPatchId = '';
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

    draw(ctx, viewer) {
        if (!this.visible || !viewer?.slideInfo) return;
        ctx.save();
        for (const patch of this.patches.values()) {
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
            ctx.fillStyle = style.fill;
            ctx.strokeStyle = (patch.str_patch_id || patch.patch_id) === this.selectedPatchId ? '#2563eb' : style.stroke;
            ctx.lineWidth = (patch.str_patch_id || patch.patch_id) === this.selectedPatchId ? 3 : 1.5;
            ctx.fillRect(cx, cy, cw, ch);
            ctx.strokeRect(cx, cy, cw, ch);
        }
        ctx.restore();
    }
}
