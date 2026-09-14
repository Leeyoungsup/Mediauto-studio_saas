import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const source = await readFile(new URL('../js/admin.js', import.meta.url), 'utf8');
const start = source.indexOf('function fmtActionPill(');
const end = source.indexOf("document.querySelectorAll('.activity-cat-tab')", start);
const context = vm.createContext({
    esc: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'),
});
vm.runInContext(source.slice(start, end), context);

test('activity details show upload correlation and escape untrusted filenames', () => {
    const html = context.fmtActivityDetail({
        str_action: 'slide.upload_chunk.failed', str_detail: 'Upload failed',
        dict_context: { filename: '<img src=x onerror=alert(1)>', upload_id: 'upload-123', http_status: 404 },
    });
    assert.ok(html.includes('upload_id: upload-123'));
    assert.ok(html.includes('http_status: 404'));
    assert.ok(html.includes('&lt;img'));
    assert.ok(!html.includes('<img'));
    assert.match(context.fmtActionPill('slide.upload_chunk.failed'), /error.*Upload chunk failed/);
});

test('annotation activity shows counts, revision and patch workflow changes', () => {
    const html = context.fmtActivityDetail({
        str_action: 'cell_annotation.status_update', str_detail: 'Saved',
        dict_context: { slide_id: 's', patch_id: 'p' },
        dict_before: { str_review_status: 'pending', revision: 'r1' },
        dict_after: { str_review_status: 'reviewed', revision: 'r2', cell_count: 0 },
    });
    assert.ok(html.includes('patch_id: p'));
    assert.ok(html.includes('cell_count: 0'));
    assert.ok(html.includes('pending → reviewed'));
    assert.ok(html.includes('r1 → r2'));
    assert.match(context.fmtActionPill('annotation.save.failed'), /error.*failed/);
});
