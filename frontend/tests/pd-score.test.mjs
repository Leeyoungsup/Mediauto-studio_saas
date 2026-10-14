import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cpsCounts } from '../js/pd-score.js';

test('flat5 ignores negative immune and Other', () => {
    const counts = {0:80, 1:700, 2:20, 3:10, 4:900};
    for (const metadata of [{class_schema:'pdl1_flat_5class'}, {pd_score:{class_schema:'pdl1_flat_5class'}}, {class_names:{2:'Positive Epithelial'}}, {class_names:{2:'Positive Tumor(Epithelial)'}}]) {
        const score = cpsCounts(counts, metadata);
        assert.equal(score.score, 30);
        assert.equal(score.viableTumor, 100);
        assert.equal(score.positiveImmune, 10);
    }
});
test('legacy seven classes retain their saved meaning', () => {
    assert.equal(cpsCounts({0:80,1:700,2:800,3:20,4:6,5:4,6:900}, {class_names:{2:'Negative Macrophage'}}).score, 30);
});
test('zero denominator and cap', () => {
    const meta = {class_schema:'pdl1_flat_5class'};
    assert.equal(cpsCounts({1:10,3:20,4:30}, meta).score, 0);
    assert.equal(cpsCounts({2:1,3:20}, meta).score, 100);
});
test('formula tooltip uses the same mapping; lung TPS unchanged', async () => {
    globalThis.document = { addEventListener() {}, body: {} };
    globalThis.window = { addEventListener() {} };
    globalThis.MutationObserver = class { observe() {} };
    const { formulaDetails } = await import('../js/quanti-formula.js');
    assert.match(formulaDetails('CPS', {0:80,1:700,2:20,3:10,4:900}, {pd_score:{class_schema:'pdl1_flat_5class'}})[2], /20 \+ 10.*100/);
    assert.match(formulaDetails('CPS', {0:80,3:20,4:6,5:4})[2], /20 \+ 10.*100/);
    assert.match(formulaDetails('TPS', {0:80,1:20,2:900})[2], /20 \/ 100/);
});
