import { cpsCounts } from './pd-score.js?v=20261014-flat5-labels';
/** Formula details for the calculations displayed by the Quanti result cards. */
let active = null;
let sequence = 0;
const entries = new WeakMap();
const fmt = value => Number(value || 0).toLocaleString('en-US', { maximumFractionDigits: 4 });

export function formulaDetails(kind, counts = {}, score = null) {
    const n = [0, 1, 2, 3].map(i => Number(counts[i] || 0));
    const total = n.reduce((a, b) => a + b, 0);
    const positive = n[1] + n[2] + n[3];
    const population = `N₀=${fmt(n[0])}, N₁=${fmt(n[1])}, N₂=${fmt(n[2])}, N₃=${fmt(n[3])}. Nᵢ = cells in intensity class i; N = their sum.`;
    const empty = 'When the denominator is zero, the displayed score is 0.';
    if (kind === 'HER2') return ['HER2 · Formula',
        'Weighted intensity = (N₁ + 2N₂ + 3N₃) / N',
        `(${fmt(n[1])} + 2 × ${fmt(n[2])} + 3 × ${fmt(n[3])}) / ${fmt(total)} = ${total ? ((n[1] + 2*n[2] + 3*n[3])/total).toFixed(2) : '0.00'}`,
        population, 'The leading 0+/1+/2+/3+ is the most frequent intensity class. Ties select the lower class. The number in parentheses is weighted intensity, not a separate clinical interpretation.', empty];
    if (kind === 'Allred') return ['ER/PR · Allred formula',
        'Allred = proportion score (PS) + intensity score (IS)',
        `Positive % = (N₁ + N₂ + N₃) / N × 100 = ${total ? (positive / total * 100).toFixed(1) : '0.0'}%`,
        'PS: no positive cells → 0; otherwise <1% → 1, <10% → 2, <33% → 3, <66% → 4, ≥66% → 5.',
        `Mean positive intensity = (N₁ + 2N₂ + 3N₃) / (N₁ + N₂ + N₃) = ${positive ? ((n[1]+2*n[2]+3*n[3])/positive).toFixed(2) : '0.00'}`,
        'IS: <0.5 → 0; <1.5 → 1; <2.5 → 2; otherwise 3. No positive cells → IS 0. Displayed interpretation: total ≥3 → Positive; otherwise Negative.', population];
    if (kind === 'KI-67') return ['KI-67 · Formula',
        'Labeling index = positive cells / total cells × 100',
        `${fmt(positive)} / ${fmt(total)} × 100 = ${total ? (positive/total*100).toFixed(1) : '0.0'}%`,
        'Positive cells = N₁ + N₂ + N₃; negative cells = N₀. Displayed interpretation: ≥14% → High; <14% → Low.', population, empty];
    if (kind === 'CPS' || kind === 'TPS') {
        const cps = cpsCounts(counts, score || {});
        const pos = kind === 'CPS' ? cps.positiveTumor : Number(counts[1] || 0);
        const immune = cps.positiveImmune;
        const denominator = pos + Number(counts[0] || 0);
        return [`PD-L1 · ${kind} formula`, kind === 'CPS'
            ? 'CPS = min(100, (positive tumor + positive immune cells) / viable tumor cells × 100)'
            : 'TPS = positive tumor cells / total tumor cells × 100',
        kind === 'CPS' ? `min(100, (${fmt(pos)} + ${fmt(immune)}) / ${fmt(denominator)} × 100)` : `${fmt(pos)} / ${fmt(denominator)} × 100`,
        'Tumor denominator = positive + negative tumor cells. Immune cells are excluded from the denominator.',
        ...(kind === 'CPS' ? ['Positive immune cells = positive lymphocytes + positive macrophages. CPS is capped at 100; the current result card displays it with a % suffix.'] : []), empty];
    }
    if (kind === 'sTIL') return ['Quanti HE · AI-estimated sTIL formula',
        'sTIL (%) = min(100, estimated immune-cell area / tumor-associated stroma area × 100)',
        'Estimated immune-cell area = (stromal lymphocytes + plasma cells) × calibrated area per immune cell.',
        ...(score?.available ? [`(${fmt(score.lymphocyte_count)} + ${fmt(score.plasma_count)}) × ${fmt(score.immune_cell_area_um2)} µm² / (${fmt(score.tumor_associated_stroma_area_mm2)} mm² × 1,000,000) × 100; capped at 100.`,
            `Reported result: ${Number(score.score_percent).toFixed(1)}%. Displayed area values are rounded; the score uses unrounded areas.`] : [`Score unavailable: ${score?.reason || 'Required tissue was not detected.'}`]),
        'Cell density (cells/mm²) = stromal cell count / tumor-associated stroma area (mm²).',
        'Uses the saved tissue-analysis result, not the current edited cell counts. Research-use estimate; requires pathologist calibration.'];
    return ['Quanti HE · Cell proportions', 'Class proportion (%) = cells in the class / total counted cells × 100.', `Total counted cells = ${fmt(Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0))}. The denominator includes all classes in the current counted result.`, 'Class counts and percentages update when result cells are edited. With no counted cells, the displayed proportion is 0%.'];
}

function close(restoreFocus = false) {
    if (!active) return;
    const { button, panel } = active;
    panel.remove(); button.setAttribute('aria-expanded', 'false'); active = null;
    if (restoreFocus) button.focus();
}
function position() {
    if (!active) return;
    const { button, panel, card } = active;
    if (!card.getClientRects().length || card.hidden || button.hidden) { close(); return; }
    const rect = button.getBoundingClientRect();
    panel.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - panel.offsetWidth - 8))}px`;
    panel.style.top = `${Math.max(8, Math.min(rect.bottom + 6, innerHeight - panel.offsetHeight - 8))}px`;
}
// Native MathML gives fractions, subscripts and operators proper math layout.
// All markup below is fixed; numeric values are formatted from Numbers only.
const mi = text => `<mi>${text}</mi>`;
const mn = value => `<mn>${fmt(value)}</mn>`;
const op = text => `<mo>${text}</mo>`;
const row = (...parts) => `<mrow>${parts.join('')}</mrow>`;
const sub = (base, index) => `<msub>${mi(base)}<mi>${index}</mi></msub>`;
const positiveN = index => `<msubsup>${mi('N')}<mi>${index}</mi>${op('+')}</msubsup>`;
const fraction = (top, bottom) => `<mfrac>${row(top)}${row(bottom)}</mfrac>`;
const equals = (label, value, percent = false) => row(`<mtext>${label}</mtext>`, op('='), value, percent ? row(op('×'), mn(100)) : '');
const nSum = row(sub('N', '1'), op('+'), sub('N', '2'), op('+'), sub('N', '3'));
const weightedN = row(sub('N', '1'), op('+'), mn(2), sub('N', '2'), op('+'), mn(3), sub('N', '3'));

function mathFormula(kind) {
    switch (kind) {
        case 'CPS': return [equals('CPS', fraction(row(positiveN('t'), op('+'), positiveN('i')), sub('N', 't')), true),
            'Nₜ⁺: PD-L1-positive tumor cells; Nᵢ⁺: PD-L1-positive lymphocytes and macrophages. Nₜ: all viable tumor cells. Reported CPS is capped at 100.'];
        case 'TPS': return [equals('TPS (%)', fraction(positiveN('t'), sub('N', 't')), true),
            'Nₜ⁺: PD-L1-positive tumor cells. Nₜ: positive + negative tumor cells.'];
        case 'HER2': return [equals('Mean intensity', fraction(weightedN, mi('N'))),
            'Nᵢ: cells in intensity class i (0–3). N: total cells across the four classes.'];
        case 'Allred': return [equals('Allred', row(mi('PS'), op('+'), mi('IS'))),
            'PS: proportion score (0–5). IS: intensity score (0–3). Total: 0–8.'];
        case 'KI-67': return [equals('KI-67 (%)', fraction(`<msup>${mi('N')}${op('+')}</msup>`, mi('N')), true),
            'N⁺: positive cells (N₁ + N₂ + N₃). N: all counted positive and negative cells.'];
        case 'sTIL': return [equals('sTIL (%)', fraction(sub('A', 'immune'), sub('A', 'stroma')), true),
            'Aimmune: estimated area of stromal lymphocytes and plasma cells. Astroma: tumor-associated stroma area. Areas use the same units; the estimate is capped at 100.'];
        default: return [equals('Class proportion (%)', fraction(sub('N', 'i'), mi('N')), true),
            'Nᵢ: cells in the selected class. N: all counted cells.'];
    }
}
function mathBlock(markup, label, primary = false) {
    const block = document.createElement('div');
    block.className = primary ? 'quanti-equation quanti-equation-primary' : 'quanti-equation';
    block.innerHTML = `<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">${markup}</math>`;
    block.querySelector('math').setAttribute('aria-label', label);
    return block;
}
function calculation(entry, index) {
    const c = entry.counts || {};
    const n = [0, 1, 2, 3].map(i => Number(c[i] || 0));
    const total = n.reduce((a, b) => a + b, 0), pos = n[1] + n[2] + n[3];
    const weighted = mn(n[1] + 2*n[2] + 3*n[3]);
    const result = value => row(op('='), `<mn>${value}</mn>`);
    if (index === 2 && entry.kind === 'HER2' && total) return row(fraction(weighted, mn(total)), result(((n[1]+2*n[2]+3*n[3])/total).toFixed(2)));
    if (index === 2 && entry.kind === 'KI-67' && total) return row(fraction(mn(pos), mn(total)), op('×'), mn(100), result((pos/total*100).toFixed(1)), op('%'));
    if (index === 2 && entry.kind === 'Allred' && total) return row(equals('Positive (%)', fraction(mn(pos), mn(total)), true), result((pos/total*100).toFixed(1)));
    if (index === 4 && entry.kind === 'Allred' && pos) return row(equals('Mean intensity', fraction(weighted, mn(pos))), result(((n[1]+2*n[2]+3*n[3])/pos).toFixed(2)));
    if (index === 2 && ['CPS', 'TPS'].includes(entry.kind)) {
        const cps = cpsCounts(c, entry.score || {});
        const tumor = entry.kind === 'CPS' ? cps.positiveTumor : Number(c[1] || 0), denominator = tumor + Number(c[0] || 0);
        const immune = cps.positiveImmune;
        if (!denominator) return null;
        const top = entry.kind === 'CPS' ? row(mn(tumor), op('+'), mn(immune)) : mn(tumor);
        return row(fraction(top, mn(denominator)), op('×'), mn(100));
    }
    if (index === 3 && entry.kind === 'sTIL' && entry.score?.available) {
        const s = entry.score;
        const area = Number(s.tumor_associated_stroma_area_mm2);
        if (area > 0) return row(fraction(row(mn(Number(s.lymphocyte_count || 0) + Number(s.plasma_count || 0)), op('×'), mn(s.immune_cell_area_um2)), row(mn(area), op('×'), mn(1000000))), op('×'), mn(100));
    }
    return null;
}

function render(entry) {
    entry.panel.replaceChildren();
    entry.details.forEach((text, i) => {
        if (i === 1) {
            const [markup, definition] = mathFormula(entry.kind);
            entry.panel.append(mathBlock(markup, text, true));
            const note = document.createElement('p'); note.className = 'quanti-symbols'; note.textContent = definition;
            entry.panel.append(note);
            return;
        }
        const numericMath = calculation(entry, i);
        if (numericMath) {
            entry.panel.append(mathBlock(numericMath, text));
            return;
        }
        const element = document.createElement(i ? 'p' : 'h3');
        const zeroCountEquation = i === 2 && ['HER2', 'KI-67', 'CPS', 'TPS', 'Allred'].includes(entry.kind);
        element.textContent = zeroCountEquation ? 'No cells in the denominator. The application displays 0 (0.00 for weighted intensity).' : text;
        if (!i) element.id = `${entry.panel.id}-title`;
        entry.panel.append(element);
    });
    const dismiss = document.createElement('button');
    dismiss.type = 'button'; dismiss.className = 'quanti-formula-close'; dismiss.textContent = 'Close';
    dismiss.addEventListener('click', () => close(true)); entry.panel.append(dismiss);
}
export function setQuantiFormula(card, kind, counts, score) {
    if (!card) return;
    let entry = entries.get(card);
    if (!entry) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'quanti-formula-trigger'; button.textContent = 'Formula ▾';
        button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-haspopup', 'dialog');
        const panel = document.createElement('div'); panel.className = 'quanti-formula-popover';
        panel.id = `quanti-formula-${++sequence}`; panel.setAttribute('role', 'dialog'); panel.tabIndex = -1;
        panel.setAttribute('aria-labelledby', `${panel.id}-title`); button.setAttribute('aria-controls', panel.id);
        entry = { button, panel, card }; entries.set(card, entry); card.append(button);
        button.addEventListener('click', () => {
            if (active === entry) { close(); return; }
            close(); render(entry); document.body.append(panel); active = entry;
            button.setAttribute('aria-expanded', 'true'); position(); panel.focus();
        });
    }
    entry.kind = kind; entry.counts = counts; entry.score = score;
    entry.details = formulaDetails(kind, counts, score);
    entry.button.setAttribute('aria-label', `${kind} formula`);
    if (active === entry) { render(entry); position(); }
}
document.addEventListener('pointerdown', event => {
    if (active && !active.panel.contains(event.target) && !active.button.contains(event.target)) close();
});
document.addEventListener('keydown', event => { if (active && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); } }, true);
document.addEventListener('focusin', event => {
    if (active && !active.panel.contains(event.target) && event.target !== active.button) close();
});
window.addEventListener('resize', position);
document.addEventListener('scroll', position, true);
new MutationObserver(() => { if (active) position(); }).observe(document.body, { attributes: true, subtree: true, attributeFilter: ['hidden', 'class'] });

export function setQuantiCountFormula(header, counts, enabled) {
    if (!header) return;
    if (enabled) {
        header.classList.add('quanti-count-formula-host');
        setQuantiFormula(header, 'Cell proportions', counts);
    }
    const entry = entries.get(header);
    if (entry) {
        entry.button.hidden = !enabled;
        if (!enabled && active === entry) close();
    }
}
