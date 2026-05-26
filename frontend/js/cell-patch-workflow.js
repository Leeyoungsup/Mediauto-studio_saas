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
        this.editor = new CellAnnotationEditor({
            api,
            viewer,
            statusLayer: this.status,
            onStatus: this.setStatus,
            onSaved: (patch) => this.updatePatch(patch),
        });
        this.viewer.addOverlayLayer(this.required);
        this.viewer.addOverlayLayer(this.status);
        this.viewer.addOverlayLayer(this.grid);
        this._bindEvents();
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
        }, true);
    }

    async load(slideId) {
        this.slideId = slideId || '';
        this.patches.clear();
        this.editor.close();
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
        this.viewer.requestRender();
    }

    updatePatch(patch) {
        const id = patch.str_patch_id || patch.patch_id;
        if (!id) return;
        this.patches.set(id, { ...patch, patch_id: id });
        this.status.setPatches(Array.from(this.patches.values()));
        this.viewer.requestRender();
    }

    async addRequiredRegionFromAnnotation(annotation) {
        if (!this.slideId || !annotation) return;
        const coords = annotation.coordinates || [];
        if (coords.length < 3) return;
        const regions = this.required.toApiRegions();
        regions.push({
            id: `region_${Date.now()}`,
            type: 'annotation_required_region',
            points: coords.map(pt => [Number(pt[0]), Number(pt[1])]),
        });
        await this.api.saveCellRequiredRegions(this.slideId, regions);
        await this.api.recomputeCellPatchStatus(this.slideId);
        const regionPayload = await this.api.getCellRequiredRegions(this.slideId);
        this.required.setRegions(regionPayload.regions || []);
        await this.refreshPatches();
        this.setStatus('Required region saved and patch status recomputed');
    }
}
