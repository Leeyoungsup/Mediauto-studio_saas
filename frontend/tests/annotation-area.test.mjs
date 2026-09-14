import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const moduleUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const areaSource = await readFile(new URL('../js/annotation-area.js', import.meta.url), 'utf8');
const { fixedAreaCoordinates, annotationAreaMm2, annotationAreaLabel } = await import(moduleUrl(areaSource));
let viewerSource = await readFile(new URL('../js/tile-viewer.js', import.meta.url), 'utf8');
viewerSource = viewerSource.replace(/import \{ api \} from '[^']+';/, 'const api = {};')
    .replace(/from '\.\/annotation-area\.js[^']*'/, `from '${moduleUrl(areaSource)}'`);
const { TileViewer } = await import(moduleUrl(viewerSource));

for (const shape of ['rectangle', 'circle']) {
    for (const area of [1, 2, 4, 8]) {
        test(`${shape} is ${area} mm² with unequal pixel spacing`, () => {
            const info = { mpp_x: 0.25, mpp_y: 0.5 };
            const coordinates = fixedAreaCoordinates(shape, 100000, 90000, area, info);
            const annotation = { type: shape === 'circle' ? 'polygon' : shape, coordinates };
            assert.ok(Math.abs(annotationAreaMm2(annotation, info) - area) < 1e-8);
            assert.equal(annotationAreaLabel(annotation, info), `${area}.00 mm²`);
        });
    }
}

test('area reflects edited geometry and does not invent missing calibration', () => {
    const annotation = { type: 'rectangle', coordinates: [[0, 0], [1000, 0], [1000, 1000], [0, 1000]] };
    assert.equal(annotationAreaLabel(annotation, { mpp: 1 }), '1.00 mm²');
    annotation.coordinates[1][0] = annotation.coordinates[2][0] = 2000;
    assert.equal(annotationAreaLabel(annotation, { mpp: 1 }), '2.00 mm²');
    assert.equal(annotationAreaLabel(annotation, {}), 'Area unavailable');
    assert.equal(annotationAreaLabel({ type: 'point' }, { mpp: 1 }), '');
    assert.equal(fixedAreaCoordinates('rectangle', 0, 0, 2, { mpp: 0 }), null);
});

test('AI and Tissue default to 2 mm²; Cell preserves 1 mm² tools and hides labels', () => {
    const viewer = Object.create(TileViewer.prototype);
    viewer.slideInfo = { mpp: 0.25 };
    for (const kind of ['ai', 'tissue-annotation']) {
        viewer.viewerKind = kind;
        const annotation = { type: 'rectangle', coordinates: viewer._makeRect1mm2Coords(0, 0) };
        assert.equal(viewer.getAnnotationAreaLabel(annotation), '2.00 mm²');
    }
    viewer.viewerKind = 'cell-annotation';
    const annotation = { type: 'rectangle', coordinates: viewer._makeRect1mm2Coords(0, 0) };
    assert.equal(annotationAreaMm2(annotation, viewer.slideInfo), 1);
    assert.equal(viewer._makeCircle1mm2Coords(0, 0).length, 64);
    assert.equal(viewer.getAnnotationAreaLabel(annotation), '');
});

test('partly clipped annotation label stays inside the viewport', () => {
    const viewer = Object.create(TileViewer.prototype);
    Object.assign(viewer, { viewerKind: 'ai', slideInfo: { mpp: 1 }, _viewW: 800, _viewH: 600,
        sceneToCanvas: (x, y) => [x, y] });
    const draws = [];
    const context = { save() {}, restore() {}, measureText: () => ({ width: 70 }),
        fillRect: (...args) => draws.push(args), fillText() {} };
    viewer._drawAnnotationArea(context, { type: 'rectangle', coordinates: [[-50, -50], [100, -50], [100, 100], [-50, 100]] });
    assert.deepEqual(draws[0], [4, 4, 82, 22]);
});
