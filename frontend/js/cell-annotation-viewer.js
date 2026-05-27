import { TileViewer } from './tile-viewer.js?v=20260527-06';
import { VIEWER_CAPABILITIES, applyViewerCapabilities } from './viewer-capabilities.js?v=20260526-01';

export class CellAnnotationViewer extends TileViewer {
    constructor(canvas, overlayCanvas) {
        super(canvas, overlayCanvas);
        applyViewerCapabilities(this, VIEWER_CAPABILITIES.cellAnnotation);
    }
}
