import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { webcrypto } from 'node:crypto';
import vm from 'node:vm';

const source = (await readFile(new URL('../js/pd-l1-comparison.js', import.meta.url), 'utf8'))
    .replace(/^import .*;\n/gm, '').replace(/^export /gm, '');
const context = vm.createContext({ crypto: webcrypto });
vm.runInContext(source, context);
const createId = context.createComparisonRunId;
const uuid4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

test('prefers native UUID when available', () => {
    const provider = { randomUUID() { assert.equal(this, provider); return 'native-id'; } };
    assert.equal(createId(provider), 'native-id');
});

test('HTTP fallback produces distinct UUIDv4 values accepted by the API schema', () => {
    const provider = { getRandomValues: bytes => webcrypto.getRandomValues(bytes) };
    const ids = Array.from({ length: 1000 }, () => createId(provider));
    for (const id of ids) assert.match(id, uuid4);
    assert.equal(new Set(ids).size, ids.length);
});

test('UUID fallback sets version and variant bits without discarding other bytes', () => {
    assert.equal(createId({ getRandomValues: bytes => bytes.fill(255) }),
        'ffffffff-ffff-4fff-bfff-ffffffffffff');
});

test('unsupported crypto reports an actionable error instead of a TypeError', () => {
    assert.throws(() => createId(null), /최신 브라우저/);
    assert.throws(() => createId({}), /최신 브라우저/);
});
