import { TileViewer } from './tile-viewer.js?v=20260824-01';
import { VIEWER_CAPABILITIES, applyViewerCapabilities } from './viewer-capabilities.js?v=20260526-01';

export class AiViewer extends TileViewer {
    constructor(canvas, overlayCanvas) {
        super(canvas, overlayCanvas);
        // Heatmap is explicitly enabled from Detection Results. Detailed
        // individual-cell geometry is available at 5 µm/px and closer.
        this.detailedCellMppThreshold = 5.0;
        this.maxIndividualDetectionCells = 50000;
        this.denseCellPointSize = 2.0;
        applyViewerCapabilities(this, VIEWER_CAPABILITIES.ai);
    }
}
