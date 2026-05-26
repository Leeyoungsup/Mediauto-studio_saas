export class WsiRequiredRegionLayer {
    constructor(options = {}) {
        this.regions = [];
        this.visible = options.visible !== false;
    }

    setRegions(regions = []) {
        this.regions = Array.isArray(regions) ? regions : [];
    }

    toApiRegions() {
        return this.regions.map((region, idx) => ({
            id: region.str_region_id || region.id || `region_${idx + 1}`,
            type: 'annotation_required_region',
            points: (region.list_points || region.points || region.coordinates || []).map(pt => (
                Array.isArray(pt) ? [Number(pt[0]), Number(pt[1])] : [Number(pt.x), Number(pt.y)]
            )),
        }));
    }

    draw(ctx, viewer) {
        if (!this.visible || !viewer?.slideInfo) return;
        ctx.save();
        ctx.lineWidth = 2;
        ctx.strokeStyle = 'rgba(244, 63, 94, 0.95)';
        ctx.fillStyle = 'rgba(244, 63, 94, 0.10)';
        ctx.setLineDash([8, 5]);
        for (const region of this.regions) {
            const points = region.list_points || region.points || region.coordinates || [];
            if (!points || points.length < 3) continue;
            ctx.beginPath();
            points.forEach((pt, idx) => {
                const x = Array.isArray(pt) ? pt[0] : pt.x;
                const y = Array.isArray(pt) ? pt[1] : pt.y;
                const [cx, cy] = viewer.sceneToCanvas(Number(x), Number(y));
                if (idx === 0) ctx.moveTo(cx, cy);
                else ctx.lineTo(cx, cy);
            });
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
        }
        ctx.restore();
    }
}
