export const VIEWER_CAPABILITIES = Object.freeze({
    ai: Object.freeze({
        kind: 'ai',
        aiAnalysis: true,
        tissueAnnotation: false,
        cellAnnotation: false,
        virtualStain: true,
        resultCells: true,
    }),
    tissueAnnotation: Object.freeze({
        kind: 'tissue-annotation',
        aiAnalysis: true,
        tissueAnnotation: true,
        cellAnnotation: false,
        virtualStain: true,
        resultCells: true,
    }),
    cellAnnotation: Object.freeze({
        kind: 'cell-annotation',
        aiAnalysis: true,
        tissueAnnotation: false,
        cellAnnotation: true,
        virtualStain: true,
        resultCells: true,
    }),
});

export function applyViewerCapabilities(viewer, capabilities) {
    viewer.viewerKind = capabilities.kind;
    viewer.capabilities = capabilities;
    return viewer;
}
