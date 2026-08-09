import { TileViewer } from './tile-viewer.js?v=20260810-02';
import { VIEWER_CAPABILITIES, applyViewerCapabilities } from './viewer-capabilities.js?v=20260526-01';

export class AiViewer extends TileViewer {
    constructor(canvas, overlayCanvas) {
        super(canvas, overlayCanvas);
        // AI overview keeps the heatmap only at the more distant levels;
        // individual cells begin at effective MPP below 7.0 µm/px.
        this.detectionHeatmapMppThreshold = 7.0;
        applyViewerCapabilities(this, VIEWER_CAPABILITIES.ai);
    }
}
