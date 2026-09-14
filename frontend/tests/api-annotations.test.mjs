import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('annotation client carries revisions and preserves edits on conflicts', async () => {
    const previousStorage = globalThis.localStorage;
    const previousFetch = globalThis.fetch;
    globalThis.localStorage = {
        getItem: key => key === 'token_expires' ? String(Date.now() + 3600000) : '',
    };
    try {
        const source = await readFile(new URL('../js/api.js', import.meta.url), 'utf8');
        const { api } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
        let count = 0;
        const edits = [{ memo: 'my edits' }];
        globalThis.fetch = async (url, options = {}) => {
            count += 1;
            if (url.endsWith('/load')) return new Response('[]', { headers: { ETag: '"revision-1"' } });
            assert.equal(options.headers['If-Match'], '"revision-1"');
            assert.deepEqual(JSON.parse(options.body.get('data')), edits);
            return new Response('{}', { status: 409 });
        };
        await assert.rejects(api.saveAnnotations('slide', edits), /Load annotations/);
        assert.equal(count, 0);
        assert.deepEqual(await api.loadAnnotations('slide'), []);
        await assert.rejects(api.saveAnnotations('slide', edits), /Export|export/);
        assert.deepEqual(edits, [{ memo: 'my edits' }]);
        globalThis.fetch = async (_url, options) => {
            assert.equal(options.headers['If-Match'], '"revision-1"');
            return Response.json({ status: 'saved', revision: '"revision-2"' });
        };
        await api.saveAnnotations('slide', edits);
        globalThis.fetch = async (_url, options) => {
            assert.equal(options.headers['If-Match'], '"revision-2"');
            return Response.json({ status: 'saved', revision: '"revision-3"' });
        };
        await api.saveAnnotations('slide', edits);
        globalThis.fetch = async () => new Response('{}', { status: 500 });
        await assert.rejects(api.loadAnnotations('slide'));
        await assert.rejects(api.saveAnnotations('slide', edits), /Load annotations/);
    } finally {
        globalThis.localStorage = previousStorage;
        globalThis.fetch = previousFetch;
    }
});
