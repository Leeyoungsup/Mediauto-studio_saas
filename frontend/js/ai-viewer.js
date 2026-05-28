import { TileViewer } from './tile-viewer.js?v=20260528-01';
import { VIEWER_CAPABILITIES, applyViewerCapabilities } from './viewer-capabilities.js?v=20260526-01';

export class AiViewer extends TileViewer {
    constructor(canvas, overlayCanvas) {
        super(canvas, overlayCanvas);
        applyViewerCapabilities(this, VIEWER_CAPABILITIES.ai);
    }
}
