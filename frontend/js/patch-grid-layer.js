export class PatchGridLayer {
    constructor(options = {}) {
        this.config = null;
        this.visible = options.visible !== false;
        this.color = options.color || 'rgba(99, 102, 241, 0.42)';
        this.lineWidth = options.lineWidth || 1;
        this.minScreenStep = options.minScreenStep || 18;
    }

    setConfig(config) {
        this.config = config || null;
    }

    patchAt(sceneX, sceneY) {
        if (!this.config) return null;
        const size = Number(this.config.patch_size_slide_px || 0);
        if (size <= 0) return null;
        const px = Math.floor(sceneX / size);
        const py = Math.floor(sceneY / size);
        if (px < 0 || py < 0 || px >= this.config.cols || py >= this.config.rows) return null;
        const x = px * size;
        const y = py * size;
        return {
            patch_id: `px_${Math.round(x)}_py_${Math.round(y)}`,
            px,
            py,
            x,
            y,
            w: Math.min(size, this.config.slide_width - x),
            h: Math.min(size, this.config.slide_height - y),
        };
    }

    draw(ctx, viewer) {
        if (!this.visible || !this.config || !viewer?.slideInfo) return;
        const size = Number(this.config.patch_size_slide_px || 0);
        if (size <= 0) return;
        const screenStep = size * viewer.zoom;
        if (screenStep < this.minScreenStep) return;

        const [sx0, sy0] = viewer.canvasToScene(0, 0);
        const [sx1, sy1] = viewer.canvasToScene(viewer._viewW, viewer._viewH);
        const xStart = Math.max(0, Math.floor(Math.min(sx0, sx1) / size) * size);
        const yStart = Math.max(0, Math.floor(Math.min(sy0, sy1) / size) * size);
        const xEnd = Math.min(this.config.slide_width, Math.ceil(Math.max(sx0, sx1) / size) * size);
        const yEnd = Math.min(this.config.slide_height, Math.ceil(Math.max(sy0, sy1) / size) * size);

        ctx.save();
        ctx.strokeStyle = this.color;
        ctx.lineWidth = this.lineWidth;
        ctx.beginPath();
        for (let x = xStart; x <= xEnd; x += size) {
            const [cx0, cy0] = viewer.sceneToCanvas(x, yStart);
            const [cx1, cy1] = viewer.sceneToCanvas(x, yEnd);
            ctx.moveTo(cx0, cy0);
            ctx.lineTo(cx1, cy1);
        }
        for (let y = yStart; y <= yEnd; y += size) {
            const [cx0, cy0] = viewer.sceneToCanvas(xStart, y);
            const [cx1, cy1] = viewer.sceneToCanvas(xEnd, y);
            ctx.moveTo(cx0, cy0);
            ctx.lineTo(cx1, cy1);
        }
        ctx.stroke();
        ctx.restore();
    }
}
