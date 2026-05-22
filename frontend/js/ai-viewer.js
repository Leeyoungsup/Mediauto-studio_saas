import { TileViewer } from './tile-viewer.js?v=20260522-11';
import { VIEWER_CAPABILITIES, applyViewerCapabilities } from './viewer-capabilities.js?v=20260522-11';

export class AiViewer extends TileViewer {
    constructor(canvas, overlayCanvas) {
        super(canvas, overlayCanvas);
        applyViewerCapabilities(this, VIEWER_CAPABILITIES.ai);
    }
}
