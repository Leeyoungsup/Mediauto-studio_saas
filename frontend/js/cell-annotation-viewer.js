import { TileViewer } from './tile-viewer.js?v=20260522-04';
import { VIEWER_CAPABILITIES, applyViewerCapabilities } from './viewer-capabilities.js?v=20260522-04';

export class CellAnnotationViewer extends TileViewer {
    constructor(canvas, overlayCanvas) {
        super(canvas, overlayCanvas);
        applyViewerCapabilities(this, VIEWER_CAPABILITIES.cellAnnotation);
    }
}
