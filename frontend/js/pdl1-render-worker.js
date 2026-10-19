import { TileViewer } from './tile-viewer.js?v=20261019-cell-export-01';
import { _normalizeAiResultPayload } from './api.js?v=20261019-cell-export-01';

self.onmessage = event => {
    try {
        const payload = JSON.parse(new TextDecoder().decode(event.data.bytes));
        const result = _normalizeAiResultPayload(payload.result);
        const view = event.data.viewport;
        if (!view || !result || !Array.isArray(result.cells)) throw Error('AI 그리기 데이터가 없습니다.');
        const canvas = new OffscreenCanvas(Math.max(1,Math.round(view.width*view.dpr)), Math.max(1,Math.round(view.height*view.dpr)));
        // Reuse the real viewer's indexing, heatmap preparation and cell renderer.
        // No constructor, DOM listeners, tiles, or visible canvas are involved.
        const renderer = Object.create(TileViewer.prototype);
        Object.assign(renderer, {
            slideInfo:{mpp:view.mpp},_viewW:view.width,_viewH:view.height,_dpr:view.dpr,
            viewCenterX:view.centerX,viewCenterY:view.centerY,zoom:view.zoom,
            defaultConfidence:.1,classColorOverride:result.class_colors||null,
            detailedCellMppThreshold:5,maxIndividualDetectionCells:50000,denseCellPointSize:2,
            requestRender() {},
        });
        const started = performance.now();
        renderer.setDetectionResults(result.cells);
        renderer.setHiddenDetectionResults(result.excluded_cells||[]);
        const context = canvas.getContext('2d');
        context.setTransform(view.dpr,0,0,view.dpr,0,0);
        renderer._renderCells(context);
        // Read back pixels to ensure rasterization has completed before reporting success.
        context.getImageData(0,0,canvas.width,canvas.height);
        const { result: ignored, ...summary } = payload;
        self.postMessage({...summary,rendered:true,render_elapsed_ms:performance.now()-started,
                          rendered_cell_count:renderer.detectionCells.length});
    } catch(error) { self.postMessage({error:error.message}); }
};
