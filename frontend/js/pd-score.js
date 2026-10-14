/** Interpret saved PD-L1 class IDs without reclassifying legacy results. */
export function cpsCounts(counts = {}, metadata = {}) {
    const names = metadata.class_names || metadata.classNames || {};
    const schema = metadata.class_schema || metadata.pd_score?.class_schema || metadata.model_runtime?.class_schema;
    const flat5 = schema === 'pdl1_flat_5class' || ['positive epithelial', 'positive tumor(epithelial)'].includes(String(names[2] || '').toLowerCase());
    const positiveTumorId = flat5 ? 2 : 3;
    const positiveImmuneIds = flat5 ? [3] : [4, 5];
    const positiveTumor = Number(counts[positiveTumorId] || 0);
    const positiveImmune = positiveImmuneIds.reduce((sum, id) => sum + Number(counts[id] || 0), 0);
    const negativeTumor = Number(counts[0] || 0);
    const viableTumor = negativeTumor + positiveTumor;
    return { positiveTumor, positiveImmune, negativeTumor, viableTumor,
        positiveTumorId, positiveImmuneIds,
        score: viableTumor ? Math.min(100, (positiveTumor + positiveImmune) / viableTumor * 100) : 0 };
}
