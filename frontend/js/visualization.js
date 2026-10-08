/**
 * AI Detection Result Visualization
 * text detection_visualization_dialog.pytext text Canvastext text
 * 4text text: Class Distribution, Tumor Analysis, Spatial Heatmap, Confidence Distribution
 */

const DEFAULT_CLASS_NAMES = {
    0: 'Neutrophil', 1: 'Epithelial', 2: 'Lymphocyte', 3: 'Plasma',
    4: 'Eosinophil', 5: 'Stromal cell', 6: 'Tumor Epithelial', 7: 'Benign Epithelial',
};
const DEFAULT_CLASS_COLORS = {
    0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
    4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
};
// text text text text (showVisualization text text text)
let _activeNames = DEFAULT_CLASS_NAMES;
let _activeColors = DEFAULT_CLASS_COLORS;
let _activeModelType = 'Quanti HE';  // 'Quanti HE' | 'Quanti PD-L1' | 'Quanti IHC'
let _activeScoreType = null;      // 'CPS' | 'TPS' | 'HER2' | 'Allred' | null
let _activeTissue = null;

function _getName(id) { return _activeNames[id] || DEFAULT_CLASS_NAMES[id] || `Class ${id}`; }
function _getColor(id) { return _activeColors[id] || DEFAULT_CLASS_COLORS[id] || '#888'; }

// text text text (text text text text text text)
const CLASS_NAMES = new Proxy({}, { get: (_, k) => _getName(k) });
const CLASS_COLORS = new Proxy({}, { get: (_, k) => _getColor(k) });

const $vizDialog = document.querySelector('#viz-dialog');
const $closeViz = document.querySelector('#close-viz');

// Tab switching
$vizDialog?.querySelectorAll('.viz-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        $vizDialog.querySelectorAll('.viz-tab').forEach(t => t.classList.remove('active'));
        $vizDialog.querySelectorAll('.viz-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab)?.classList.add('active');
    });
});
$closeViz?.addEventListener('click', () => $vizDialog.close());

// text text text text (PDF exporttext)
let _vizState = null;

/**
 * text text text
 * @param {Array} cells - [{x, y, class_id, confidence}, ...]
 * @param {Object|null} segData - {thumbnail, overlays, class_names, width, height}
 */
export function showVisualization(cells, segData = null, thumbnailUrl = null, meta = {}) {
    if (!$vizDialog || !cells || cells.length === 0) return;

    // text text text (text/text/text)
    _activeNames = (meta.classNames && Object.keys(meta.classNames).length > 0)
        ? _normalizeKeys(meta.classNames) : DEFAULT_CLASS_NAMES;
    _activeColors = (meta.classColors && Object.keys(meta.classColors).length > 0)
        ? _normalizeKeys(meta.classColors) : DEFAULT_CLASS_COLORS;
    _activeModelType = meta.modelType || 'Quanti HE';
    _activeScoreType = meta.scoreType || null;
    _activeTissue = meta.tissue || 'Stomach';
    const stilScore = meta.stilScore || null;

    // text text text
    const countsByClass = {};
    const confsByClass = {};
    for (const c of cells) {
        const id = c.class_id;
        countsByClass[id] = (countsByClass[id] || 0) + 1;
        if (!confsByClass[id]) confsByClass[id] = [];
        confsByClass[id].push(c.confidence);
    }

    _vizState = {
        cells, countsByClass, confsByClass, segData,
        thumbnailUrl, thumbnailImg: null,
        slideName: meta.slideName || 'slide',
        tissue: _activeTissue,
        slideDims: meta.slideDims || null,
        modelType: _activeModelType,
        classNames: _activeNames,
        classColors: _activeColors,
        stilScore,
    };

    // text text text (PDFtext) — same-origintext crossOrigin text
    if (thumbnailUrl) {
        const img = new Image();
        img.onload = () => { if (_vizState) _vizState.thumbnailImg = img; };
        img.onerror = (e) => console.warn('[viz] thumbnail preload failed', e);
        img.src = thumbnailUrl;
    }

    // text text text text text text
    _configureTabs(_activeModelType, Boolean(stilScore?.available));

    _renderClassDistribution(cells, countsByClass);
    if (_activeModelType === 'Quanti PD-L1') {
        _renderPdScoreAnalysis(countsByClass);
    } else if (_activeModelType === 'Quanti IHC') {
        if (_activeScoreType === 'Allred') {
            _renderAllredAnalysis(countsByClass);
        } else if (_activeScoreType === 'KI67') {
            _renderKi67Analysis(countsByClass);
        } else {
            _renderHer2Analysis(countsByClass);
        }
    } else {
        _renderTumorAnalysis(countsByClass);
    }
    if (_activeModelType !== 'Quanti PD-L1' && _activeModelType !== 'Quanti IHC') {
        _renderSpatialHeatmap(cells, countsByClass, segData);
    }
    if (stilScore?.available) {
        _renderStilAnalysis(stilScore);
        _renderStilSpatialHeatmap(document.getElementById('viz-stil-heatmap'), stilScore);
    }
    _renderConfidenceDistribution(confsByClass);

    // text text text text text
    const tabs = Array.from($vizDialog.querySelectorAll('.viz-tab')).filter(t => !t.hidden);
    const panels = Array.from($vizDialog.querySelectorAll('.viz-panel'));
    $vizDialog.querySelectorAll('.viz-tab').forEach(t => t.classList.remove('active'));
    panels.forEach(p => p.classList.remove('active'));
    if (tabs.length > 0) {
        tabs[0].classList.add('active');
        document.getElementById(tabs[0].dataset.tab)?.classList.add('active');
    }

    $vizDialog.showModal();
}

function _normalizeKeys(obj) {
    const out = {};
    for (const [k, v] of Object.entries(obj)) out[parseInt(k)] = v;
    return out;
}

function _configureTabs(modelType, hasStilScore = false) {
    const isPdScore = modelType === 'Quanti PD-L1';
    const isIhc = modelType === 'Quanti IHC';
    const hideHeatmap = isPdScore || isIhc;
    let tumorLabel = 'Tumor Analysis';
    if (isPdScore) tumorLabel = 'CPS / TPS Analysis';
    else if (isIhc) tumorLabel = (_activeScoreType === 'Allred') ? 'Allred Analysis' : (_activeScoreType === 'KI67') ? 'KI-67 Analysis' : 'HER2 Analysis';

    const tabButtons = $vizDialog.querySelectorAll('.viz-tab');
    tabButtons.forEach(tab => {
        const name = tab.dataset.tab;
        if (name === 'viz-tumor') {
            tab.textContent = tumorLabel;
        }
        if (name === 'viz-heatmap') {
            tab.hidden = hideHeatmap;
            tab.style.display = hideHeatmap ? 'none' : '';
        }
        if (name === 'viz-stil' || name === 'viz-stil-heatmap') {
            tab.hidden = !hasStilScore;
            tab.style.display = hasStilScore ? '' : 'none';
        }
    });
    const heatmapPanel = document.getElementById('viz-heatmap');
    if (heatmapPanel) {
        heatmapPanel.style.display = hideHeatmap ? 'none' : '';
        if (hideHeatmap) heatmapPanel.classList.remove('active');
    }
}

// Export PDF text
const $btnExportPdf = document.querySelector('#btn-export-pdf');
$btnExportPdf?.addEventListener('click', async () => {
    if (!_vizState) return;
    const orig = $btnExportPdf.textContent;
    $btnExportPdf.textContent = 'Generating...';
    $btnExportPdf.disabled = true;
    try {
        await _exportPDF(_vizState);
    } catch (e) {
        console.error(e);
        alert('PDF generation failed: ' + e.message);
    } finally {
        $btnExportPdf.textContent = orig;
        $btnExportPdf.disabled = false;
    }
});

// ── text text ──
function _easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
function _easeOutElastic(t) {
    if (t === 0 || t === 1) return t;
    return Math.pow(2, -10 * t) * Math.sin((t - 0.075) * (2 * Math.PI) / 0.3) + 1;
}

function _animate(duration, drawFn, onDone) {
    const start = performance.now();
    function step(now) {
        const t = Math.min((now - start) / duration, 1);
        drawFn(t);
        if (t < 1) requestAnimationFrame(step);
        else if (onDone) onDone();
    }
    requestAnimationFrame(step);
}

/** HiDPI text text: CSS text text text text text text */
function _createHiDPICanvas(cssW, cssH) {
    const dpr = window.devicePixelRatio || 1;
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas.style.width = cssW + 'px';
    canvas.style.height = cssH + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    // text text text (draw text text)
    canvas._cssW = cssW;
    canvas._cssH = cssH;
    return canvas;
}

// ── Class Distribution text ──
function _renderClassDistribution(cells, countsByClass) {
    const panel = document.getElementById('viz-class-dist');
    panel.innerHTML = '';

    const active = Object.entries(countsByClass).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    if (active.length === 0) { panel.innerHTML = '<p>No detection data</p>'; return; }

    const row = document.createElement('div');
    row.className = 'viz-chart-row';
    panel.appendChild(row);

    // text text text text text text
    const panelW = panel.clientWidth || 780;
    const gap = 16;
    const barW_canvas = Math.floor((panelW - gap) * 0.52);
    const pieW_canvas = Math.floor((panelW - gap) * 0.48);

    const barH_each = Math.min(28, (280 / active.length) - 4);
    const barH_canvas = Math.max(280, active.length * (barH_each + 4) + 40);
    const barCanvas = _createHiDPICanvas(barW_canvas, barH_canvas);
    row.appendChild(barCanvas);

    const legendH = active.length * 16 + 16;
    const pieRadius = Math.min(pieW_canvas / 2 - 20, 110);
    const pieH_canvas = pieRadius * 2 + 60 + legendH;
    const pieCanvas = _createHiDPICanvas(pieW_canvas, pieH_canvas);
    row.appendChild(pieCanvas);

    const total = cells.length;
    const maxVal = Math.max(...active.map(([, v]) => v));
    const leftPad = Math.min(130, barW_canvas * 0.32);
    const rightPad = 50;
    const topPad = 30;

    _animate(800, (t) => {
        const ease = _easeOutCubic(t);

        // ── Bar chart ──
        const ctx = barCanvas.getContext('2d');
        ctx.clearRect(0, 0, barW_canvas, barH_canvas);

        ctx.fillStyle = '#000';
        ctx.font = 'bold 15px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('Cell Count by Class', leftPad, 20);

        for (let i = 0; i < active.length; i++) {
            const [idStr, count] = active[i];
            const id = parseInt(idStr);
            const y = topPad + i * (barH_each + 4);
            const fullW = (count / maxVal) * (barW_canvas - leftPad - rightPad);
            const bw = fullW * ease;

            ctx.fillStyle = 'rgba(0,0,0,0.08)';
            _roundRect(ctx, leftPad + 1, y + 1, bw, barH_each, 3);
            ctx.fill();

            const grad = ctx.createLinearGradient(leftPad, y, leftPad + bw, y);
            const baseColor = CLASS_COLORS[id] || '#888';
            grad.addColorStop(0, baseColor);
            grad.addColorStop(1, _lightenColor(baseColor, 0.2));
            ctx.fillStyle = grad;
            _roundRect(ctx, leftPad, y, Math.max(0, bw), barH_each, 3);
            ctx.fill();

            ctx.fillStyle = '#000';
            ctx.font = 'bold 13px sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(CLASS_NAMES[id] || `Class ${id}`, leftPad - 6, y + barH_each / 2 + 5);

            if (ease > 0.3) {
                ctx.textAlign = 'left';
                ctx.fillText(Math.round(count * ease).toLocaleString(), leftPad + bw + 6, y + barH_each / 2 + 5);
            }
        }

        // ── Pie chart ──
        const pctx = pieCanvas.getContext('2d');
        pctx.clearRect(0, 0, pieW_canvas, pieH_canvas);

        const cx = pieW_canvas / 2, cy = pieRadius + 30;
        const sweepTotal = Math.PI * 2 * ease;
        let startAngle = -Math.PI / 2;

        pctx.fillStyle = '#000';
        pctx.font = 'bold 15px sans-serif';
        pctx.textAlign = 'center';
        pctx.fillText(`Proportion (Total ${total.toLocaleString()})`, cx, 20);

        pctx.beginPath();
        pctx.arc(cx + 2, cy + 2, pieRadius, 0, Math.PI * 2);
        pctx.fillStyle = 'rgba(0,0,0,0.1)';
        pctx.fill();

        for (const [idStr, count] of active) {
            const id = parseInt(idStr);
            const sliceAngle = (count / total) * sweepTotal;
            pctx.beginPath();
            pctx.moveTo(cx, cy);
            pctx.arc(cx, cy, pieRadius, startAngle, startAngle + sliceAngle);
            pctx.closePath();
            pctx.fillStyle = CLASS_COLORS[id] || '#888';
            pctx.fill();
            pctx.strokeStyle = '#fff';
            pctx.lineWidth = 1.5;
            pctx.stroke();

            if (t > 0.7) {
                const pct = (count / total * 100);
                if (pct > 3) {
                    const labelAlpha = Math.min(1, (t - 0.7) / 0.3);
                    const midAngle = startAngle + sliceAngle / 2;
                    const lx = cx + Math.cos(midAngle) * pieRadius * 0.65;
                    const ly = cy + Math.sin(midAngle) * pieRadius * 0.65;
                    pctx.globalAlpha = labelAlpha;
                    pctx.fillStyle = '#fff';
                    pctx.font = 'bold 12px sans-serif';
                    pctx.textAlign = 'center';
                    pctx.fillText(`${pct.toFixed(1)}%`, lx, ly + 4);
                    pctx.globalAlpha = 1;
                }
            }
            startAngle += sliceAngle;
        }

        // text — text text
        if (t > 0.5) {
            const la = Math.min(1, (t - 0.5) / 0.3);
            pctx.globalAlpha = la;
            let ly = cy + pieRadius + 24;
            pctx.font = 'bold 12px sans-serif';
            pctx.textAlign = 'left';
            for (const [idStr, count] of active) {
                const id = parseInt(idStr);
                pctx.fillStyle = CLASS_COLORS[id] || '#888';
                pctx.fillRect(14, ly - 7, 10, 10);
                pctx.fillStyle = '#000';
                pctx.fillText(`${CLASS_NAMES[id]}  (${count.toLocaleString()})`, 30, ly);
                ly += 18;
            }
            pctx.globalAlpha = 1;
        }
    });
}

// ── Tumor Analysis text ──
function _renderTumorAnalysis(countsByClass) {
    const panel = document.getElementById('viz-tumor');
    panel.innerHTML = '';

    const tumor = countsByClass[6] || 0;
    const benign = countsByClass[7] || 0;
    const totalEpi = tumor + benign;
    const tumorRatio = totalEpi > 0 ? (tumor / totalEpi * 100) : 0;

    const row = document.createElement('div');
    row.className = 'viz-chart-row';
    panel.appendChild(row);

    const summary = document.createElement('div');
    summary.className = 'viz-summary';
    panel.appendChild(summary);

    // text text text text text
    const panelW = panel.clientWidth || 780;
    const gap = 16;
    const pieW = Math.floor((panelW - gap) * 0.45);
    const gaugeW = Math.floor((panelW - gap) * 0.55);
    const chartH = 290;

    const pieCanvas = _createHiDPICanvas(pieW, chartH);
    row.appendChild(pieCanvas);

    const gaugeCanvas = _createHiDPICanvas(gaugeW, chartH);
    row.appendChild(gaugeCanvas);

    const barColor = tumorRatio >= 50 ? '#E84040' : tumorRatio >= 20 ? '#FF8C00' : '#FFB347';
    const data = [
        { val: tumor, color: '#E84040', label: `Tumor Epithelial (${tumor.toLocaleString()})` },
        { val: benign, color: '#2196F3', label: `Benign Epithelial (${benign.toLocaleString()})` },
    ];

    _animate(900, (t) => {
        const ease = _easeOutCubic(t);
        const easeElastic = t < 0.5 ? _easeOutCubic(t * 2) : _easeOutElastic((t - 0.5) * 2) * 0.5 + 0.5;

        // ── Donut Pie ──
        const pctx = pieCanvas.getContext('2d');
        pctx.clearRect(0, 0, pieW, chartH);

        const pieCx = pieW / 2, pieCy = chartH / 2;
        const outerR = Math.min(pieCx, pieCy) - 30;
        const innerR = Math.max(20, outerR * 0.55);

        pctx.fillStyle = '#000';
        pctx.font = 'bold 15px sans-serif';
        pctx.textAlign = 'center';
        pctx.fillText('Tumor vs Benign Epithelial', pieCx, 20);

        if (totalEpi > 0) {
            const sweepTotal = Math.PI * 2 * ease;

            pctx.beginPath();
            pctx.arc(pieCx + 2, pieCy + 2, outerR, 0, Math.PI * 2);
            pctx.fillStyle = 'rgba(0,0,0,0.08)';
            pctx.fill();

            let start = -Math.PI / 2;
            for (const d of data) {
                const angle = (d.val / totalEpi) * sweepTotal;
                pctx.beginPath();
                pctx.arc(pieCx, pieCy, outerR, start, start + angle);
                pctx.arc(pieCx, pieCy, innerR, start + angle, start, true);
                pctx.closePath();
                pctx.fillStyle = d.color;
                pctx.fill();
                pctx.strokeStyle = '#fff';
                pctx.lineWidth = 2;
                pctx.stroke();

                if (t > 0.6) {
                    const pct = (d.val / totalEpi * 100);
                    if (pct > 3) {
                        const la = Math.min(1, (t - 0.6) / 0.3);
                        const mid = start + angle / 2;
                        const lr = (outerR + innerR) / 2;
                        pctx.globalAlpha = la;
                        pctx.fillStyle = '#fff';
                        pctx.font = 'bold 14px sans-serif';
                        pctx.fillText(`${pct.toFixed(1)}%`, pieCx + Math.cos(mid) * lr, pieCy + Math.sin(mid) * lr + 5);
                        pctx.globalAlpha = 1;
                    }
                }
                start += angle;
            }

            if (t > 0.4) {
                const ca = Math.min(1, (t - 0.4) / 0.3);
                pctx.globalAlpha = ca;
                pctx.fillStyle = '#000';
                pctx.font = 'bold 20px sans-serif';
                pctx.textAlign = 'center';
                pctx.fillText(Math.round(totalEpi * ease).toLocaleString(), pieCx, pieCy - 2);
                pctx.font = 'bold 12px sans-serif';
                pctx.fillStyle = '#000';
                pctx.fillText('cells', pieCx, pieCy + 16);
                pctx.globalAlpha = 1;
            }

            if (t > 0.5) {
                const la = Math.min(1, (t - 0.5) / 0.3);
                pctx.globalAlpha = la;
                let ly = chartH - 40;
                pctx.font = 'bold 13px sans-serif';
                pctx.textAlign = 'left';
                for (const d of data) {
                    pctx.fillStyle = d.color;
                    _roundRect(pctx, 14, ly - 9, 12, 12, 2); pctx.fill();
                    pctx.fillStyle = '#000';
                    pctx.fillText(d.label, 32, ly);
                    ly += 20;
                }
                pctx.globalAlpha = 1;
            }
        } else {
            pctx.fillStyle = '#000';
            pctx.font = 'bold 16px sans-serif';
            pctx.fillText('No Epithelial cells', pieCx, pieCy);
        }

        // ── Gauge ──
        const gctx = gaugeCanvas.getContext('2d');
        gctx.clearRect(0, 0, gaugeW, chartH);

        const gaugeCx = gaugeW / 2;

        gctx.fillStyle = '#000';
        gctx.font = 'bold 15px sans-serif';
        gctx.textAlign = 'center';
        gctx.fillText(`Tumor / (Tumor + Benign)  [${totalEpi.toLocaleString()} total]`, gaugeCx, 22);

        const animRatio = tumorRatio * easeElastic;
        gctx.fillStyle = barColor;
        gctx.font = 'bold 46px sans-serif';
        gctx.fillText(`${animRatio.toFixed(1)}%`, gaugeCx, 100);

        gctx.fillStyle = '#000';
        gctx.font = 'bold 13px sans-serif';
        gctx.fillText('Tumor Ratio', gaugeCx, 118);

        const barX = 20, barY = 140, barW = gaugeW - 40, barH = 28;
        gctx.fillStyle = '#e8e8e8';
        _roundRect(gctx, barX, barY, barW, barH, 6);
        gctx.fill();

        const fillW = barW * animRatio / 100;
        if (fillW > 0) {
            const grad = gctx.createLinearGradient(barX, barY, barX + fillW, barY);
            grad.addColorStop(0, _lightenColor(barColor, 0.15));
            grad.addColorStop(1, barColor);
            gctx.fillStyle = grad;
            _roundRect(gctx, barX, barY, fillW, barH, 6);
            gctx.fill();

            if (fillW > 10) {
                gctx.fillStyle = 'rgba(255,255,255,0.25)';
                _roundRect(gctx, barX, barY, fillW, barH / 2, 6);
                gctx.fill();
            }
        }

        gctx.fillStyle = '#000';
        gctx.font = 'bold 11px sans-serif';
        gctx.textAlign = 'center';
        for (const pct of [0, 25, 50, 75, 100]) {
            const x = barX + barW * pct / 100;
            gctx.fillText(`${pct}%`, x, barY + barH + 16);
            gctx.fillStyle = '#999';
            gctx.fillRect(x, barY + barH, 1, 4);
            gctx.fillStyle = '#000';
        }

        if (t > 0.7) {
            const za = Math.min(1, (t - 0.7) / 0.3);
            gctx.globalAlpha = za;
            const zones = [
                { x0: 0, x1: 20, label: 'Low', color: '#2E7D32' },
                { x0: 20, x1: 50, label: 'Moderate', color: '#E65100' },
                { x0: 50, x1: 100, label: 'High', color: '#C62828' },
            ];
            gctx.font = 'bold 11px sans-serif';
            for (const z of zones) {
                const zx = barX + barW * (z.x0 + z.x1) / 200;
                gctx.fillStyle = z.color;
                gctx.fillText(z.label, zx, barY + barH + 32);
            }
            gctx.globalAlpha = 1;
        }
    }, () => {
        summary.innerHTML = `<strong>Tumor Epithelial:</strong> ${tumor.toLocaleString()} &nbsp;|&nbsp; ` +
            `<strong>Benign Epithelial:</strong> ${benign.toLocaleString()} &nbsp;|&nbsp; ` +
            `<strong>Tumor Ratio:</strong> <span style="color:${barColor};font-weight:700">${tumorRatio.toFixed(1)}%</span>`;
        summary.style.animation = 'fadeIn 0.3s ease';
    });
}

function _renderStilAnalysis(score) {
    const panel = document.getElementById('viz-stil');
    panel.innerHTML = '';

    const scoreValue = Number(score.score_percent || 0);
    const metrics = [
        ['Lymphocyte density', `${Number(score.lymphocyte_density_cells_mm2 || 0).toLocaleString()} cells/mm²`],
        ['Plasma-cell density', `${Number(score.plasma_density_cells_mm2 || 0).toLocaleString()} cells/mm²`],
        ['Tumor-associated stroma', `${Number(score.tumor_associated_stroma_area_mm2 || 0).toFixed(2)} mm²`],
        ['Lymphocytes in stroma', Number(score.lymphocyte_count || 0).toLocaleString()],
        ['Plasma cells in stroma', Number(score.plasma_count || 0).toLocaleString()],
        ['Immune area coefficient', `${Number(score.immune_cell_area_um2 || 0).toFixed(2)} µm²/cell`],
    ];

    const header = document.createElement('div');
    header.className = 'stil-viz-header';
    header.innerHTML = `
        <div>
            <span>AI-estimated stromal TIL</span>
            <strong>${scoreValue.toFixed(1)}%</strong>
        </div>
        <p>Global area-weighted score across the analyzed tumor-associated stroma.</p>
    `;
    panel.appendChild(header);

    const grid = document.createElement('div');
    grid.className = 'stil-viz-metrics';
    metrics.forEach(([label, value]) => {
        const item = document.createElement('div');
        item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
        grid.appendChild(item);
    });
    panel.appendChild(grid);

    const warning = document.createElement('div');
    warning.className = 'stil-viz-warning';
    warning.innerHTML = `
        <strong>Calibration required</strong>
        This is an AI-estimated research metric, not a clinical ground-truth score. The current tissue model does not separately exclude in-situ tumor, necrosis, or healthy glands.
    `;
    panel.appendChild(warning);
}

// ── CPS / TPS Analysis text (PD-L1 text) ──
function _renderPdScoreAnalysis(countsByClass) {
    const panel = document.getElementById('viz-tumor');
    panel.innerHTML = '';

    const tissue = _activeTissue;
    const scores = [];

    if (tissue === 'Stomach') {
        // CPS: (pos_tumor + pos_immune) / viable_tumor × 100, cap 100
        const posTumor = countsByClass[3] || 0;
        const posImmune = (countsByClass[4] || 0) + (countsByClass[5] || 0);
        const viableTumor = (countsByClass[0] || 0) + (countsByClass[3] || 0);
        const cps = viableTumor === 0 ? 0 : Math.min(100, (posTumor + posImmune) / viableTumor * 100);
        scores.push({
            label: 'CPS',
            value: cps,
            formula: '(Positive Tumor + Positive Immune) / Viable Tumor × 100',
            detail: [
                { name: 'Positive Tumor', value: posTumor, color: _getColor(3) },
                { name: 'Positive Immune', value: posImmune, color: _getColor(4) },
                { name: 'Viable Tumor', value: viableTumor, color: _getColor(0) },
            ],
        });
        // Stomach TPS: text text / (text + text text) × 100
        const negEpi = countsByClass[0] || 0;
        const tpsStomach = (negEpi + posTumor) === 0 ? 0 : posTumor / (negEpi + posTumor) * 100;
        scores.push({
            label: 'TPS',
            value: tpsStomach,
            formula: 'Positive Epithelial / (Positive + Negative Epithelial) × 100',
            detail: [
                { name: 'Positive Epithelial', value: posTumor, color: _getColor(3) },
                { name: 'Negative Epithelial', value: negEpi, color: _getColor(0) },
            ],
        });
    } else {
        // Lung TPS: cls1 / (cls0 + cls1) × 100
        const negTumor = countsByClass[0] || 0;
        const posTumor = countsByClass[1] || 0;
        const total = negTumor + posTumor;
        const tps = total === 0 ? 0 : posTumor / total * 100;
        scores.push({
            label: 'TPS',
            value: tps,
            formula: 'Positive Tumor / (Positive + Negative Tumor) × 100',
            detail: [
                { name: 'Positive Tumor', value: posTumor, color: _getColor(1) },
                { name: 'Negative Tumor', value: negTumor, color: _getColor(0) },
            ],
        });
    }

    const row = document.createElement('div');
    row.className = 'viz-chart-row';
    panel.appendChild(row);

    const summary = document.createElement('div');
    summary.className = 'viz-summary';
    panel.appendChild(summary);

    const panelW = panel.clientWidth || 780;
    const gap = 16;
    const cardW = Math.floor((panelW - gap * (scores.length - 1)) / scores.length);
    const cardH = 320;

    const canvases = scores.map(() => _createHiDPICanvas(cardW, cardH));
    canvases.forEach(c => row.appendChild(c));

    _animate(900, (t) => {
        const ease = _easeOutCubic(t);
        const elastic = t < 0.5 ? _easeOutCubic(t * 2) : _easeOutElastic((t - 0.5) * 2) * 0.5 + 0.5;

        scores.forEach((s, i) => {
            const ctx = canvases[i].getContext('2d');
            _drawScoreCard(ctx, cardW, cardH, s, ease, elastic);
        });
    }, () => {
        summary.innerHTML = scores.map(s =>
            `<strong>${s.label}:</strong> <span style="color:${_scoreColor(s.value)};font-weight:700">${s.value.toFixed(1)}%</span>`
        ).join(' &nbsp;|&nbsp; ');
        summary.style.animation = 'fadeIn 0.3s ease';
    });
}

function _scoreColor(v) {
    return v >= 50 ? '#E84040' : v >= 20 ? '#FF8C00' : '#2E7D32';
}

// ── HER2 Analysis text (Quanti IHC text) ──
function _renderHer2Analysis(countsByClass) {
    const panel = document.getElementById('viz-tumor');
    panel.innerHTML = '';

    const n0 = countsByClass[0] || 0;
    const n1 = countsByClass[1] || 0;
    const n2 = countsByClass[2] || 0;
    const n3 = countsByClass[3] || 0;
    const total = n0 + n1 + n2 + n3;
    const weighted = total === 0 ? 0 : (0 * n0 + 1 * n1 + 2 * n2 + 3 * n3) / total;
    const dominant = total === 0 ? 0 : [n0, n1, n2, n3].indexOf(Math.max(n0, n1, n2, n3));
    // 0~3 text 0~100 text text
    const gaugePct = (weighted / 3) * 100;
    const barColor = _getColor(Math.round(weighted));

    const row = document.createElement('div');
    row.className = 'viz-chart-row';
    panel.appendChild(row);

    const summary = document.createElement('div');
    summary.className = 'viz-summary';
    panel.appendChild(summary);

    const panelW = panel.clientWidth || 780;
    const cardH = 320;

    // 1) text text text text
    const cardW1 = Math.floor(panelW * 0.5 - 8);
    const cv1 = _createHiDPICanvas(cardW1, cardH);
    row.appendChild(cv1);

    // 2) intensity text text
    const cardW2 = Math.floor(panelW * 0.5 - 8);
    const cv2 = _createHiDPICanvas(cardW2, cardH);
    row.appendChild(cv2);

    _animate(900, (t) => {
        const ease = _easeOutCubic(t);
        const elastic = t < 0.5 ? _easeOutCubic(t * 2) : _easeOutElastic((t - 0.5) * 2) * 0.5 + 0.5;

        // text: text HER2text, text weighted(0~3)text text text elastictext gaugePct text
        const ctx1 = cv1.getContext('2d');
        _drawHer2Gauge(ctx1, cardW1, cardH, weighted, dominant, gaugePct, barColor, ease, elastic);

        // text text
        const ctx2 = cv2.getContext('2d');
        _drawHer2Bars(ctx2, cardW2, cardH, [n0, n1, n2, n3], ease);
    }, () => {
        summary.innerHTML =
            `<strong>HER2:</strong> <span style="color:${barColor};font-weight:700">${dominant}+ ` +
            `(weighted ${weighted.toFixed(2)})</span> &nbsp;|&nbsp; ` +
            `Total: ${total.toLocaleString()}`;
        summary.style.animation = 'fadeIn 0.3s ease';
    });
}

function _drawHer2Gauge(ctx, w, h, weighted, dominant, gaugePct, barColor, ease, elastic) {
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;

    ctx.fillStyle = '#000';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('HER2 Score', cx, 24);

    ctx.fillStyle = '#666';
    ctx.font = '11px sans-serif';
    ctx.fillText('Weighted mean of intensity (0+ / 1+ / 2+ / 3+)', cx, 42);

    const gaugeCy = 150;
    const radius = Math.min(w * 0.35, 100);

    ctx.lineWidth = 14;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#eee';
    ctx.beginPath();
    ctx.arc(cx, gaugeCy, radius, Math.PI, Math.PI * 2);
    ctx.stroke();

    const animVal = gaugePct * elastic;
    const angle = Math.PI + Math.PI * (animVal / 100);
    const grad = ctx.createLinearGradient(cx - radius, gaugeCy, cx + radius, gaugeCy);
    grad.addColorStop(0, _lightenColor(barColor, 0.15));
    grad.addColorStop(1, barColor);
    ctx.strokeStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, gaugeCy, radius, Math.PI, angle);
    ctx.stroke();

    const animWeighted = weighted * elastic;
    ctx.fillStyle = barColor;
    ctx.font = 'bold 40px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(animWeighted.toFixed(2), cx, gaugeCy + 8);

    ctx.fillStyle = '#555';
    ctx.font = 'bold 12px sans-serif';
    ctx.fillText(`Dominant: ${dominant}+`, cx, gaugeCy + 28);
}

// ── Allred Analysis text (Quanti IHC ER/PR text) ──
function _allredFromCounts(counts) {
    const n0 = counts[0] || 0, n1 = counts[1] || 0, n2 = counts[2] || 0, n3 = counts[3] || 0;
    const total = n0 + n1 + n2 + n3;
    const pos = n1 + n2 + n3;
    const posPct = total === 0 ? 0 : pos / total * 100;
    let ps = 0;
    if (pos === 0) ps = 0;
    else if (posPct < 1) ps = 1;
    else if (posPct < 10) ps = 2;
    else if (posPct < 33) ps = 3;
    else if (posPct < 66) ps = 4;
    else ps = 5;
    let avg = 0, is_ = 0;
    if (pos > 0) {
        avg = (1 * n1 + 2 * n2 + 3 * n3) / pos;
        if (avg < 0.5) is_ = 0;
        else if (avg < 1.5) is_ = 1;
        else if (avg < 2.5) is_ = 2;
        else is_ = 3;
    }
    const ts = ps + is_;
    return { n0, n1, n2, n3, total, pos, posPct, ps, is_, avg, ts,
             interpretation: ts >= 3 ? 'Positive' : 'Negative' };
}

function _renderAllredAnalysis(countsByClass) {
    const panel = document.getElementById('viz-tumor');
    panel.innerHTML = '';

    const a = _allredFromCounts(countsByClass);
    const tsColor = a.ts >= 3 ? '#E84040' : '#2E7D32';

    const row = document.createElement('div');
    row.className = 'viz-chart-row';
    panel.appendChild(row);

    const summary = document.createElement('div');
    summary.className = 'viz-summary';
    panel.appendChild(summary);

    const panelW = panel.clientWidth || 780;
    const cardH = 320;

    const cardW1 = Math.floor(panelW * 0.5 - 8);
    const cv1 = _createHiDPICanvas(cardW1, cardH);
    row.appendChild(cv1);

    const cardW2 = Math.floor(panelW * 0.5 - 8);
    const cv2 = _createHiDPICanvas(cardW2, cardH);
    row.appendChild(cv2);

    _animate(900, (t) => {
        const ease = _easeOutCubic(t);
        const elastic = t < 0.5 ? _easeOutCubic(t * 2) : _easeOutElastic((t - 0.5) * 2) * 0.5 + 0.5;

        const ctx1 = cv1.getContext('2d');
        _drawAllredCard(ctx1, cardW1, cardH, a, tsColor, elastic);

        const ctx2 = cv2.getContext('2d');
        _drawHer2Bars(ctx2, cardW2, cardH, [a.n0, a.n1, a.n2, a.n3], ease);
    }, () => {
        summary.innerHTML =
            `<strong>Allred TS:</strong> <span style="color:${tsColor};font-weight:700">${a.ts}/8</span> ` +
            `(PS ${a.ps} + IS ${a.is_}) &nbsp;|&nbsp; ` +
            `Positive ${a.posPct.toFixed(1)}% &nbsp;|&nbsp; ` +
            `<span style="color:${tsColor};font-weight:700">${a.interpretation}</span> ` +
            `&nbsp;|&nbsp; Total ${a.total.toLocaleString()}`;
        summary.style.animation = 'fadeIn 0.3s ease';
    });
}

function _drawAllredCard(ctx, w, h, a, tsColor, elastic) {
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;

    ctx.fillStyle = '#000';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Allred Score', cx, 24);

    ctx.fillStyle = '#666';
    ctx.font = '11px sans-serif';
    ctx.fillText('Proportion (0-5) + Intensity (0-3) = Total (0-8)', cx, 42);

    // text TS text
    const cyTs = 130;
    const animTs = a.ts * elastic;
    ctx.fillStyle = tsColor;
    ctx.font = 'bold 64px sans-serif';
    ctx.fillText(`${animTs.toFixed(0)} / 8`, cx, cyTs);

    ctx.fillStyle = '#555';
    ctx.font = 'bold 13px sans-serif';
    ctx.fillText(a.interpretation, cx, cyTs + 24);

    // text PS / IS / Pos%
    ctx.fillStyle = '#333';
    ctx.font = 'bold 12px sans-serif';
    ctx.textAlign = 'left';
    let dy = 200;
    const items = [
        ['Proportion Score (PS)', `${a.ps}  (${a.posPct.toFixed(1)}% positive)`],
        ['Intensity Score (IS)', `${a.is_}  (avg ${a.avg.toFixed(2)})`],
        ['Total Score (TS)',     `${a.ts}  (${a.interpretation})`],
    ];
    for (const [k, v] of items) {
        ctx.fillStyle = '#666';
        ctx.fillText(k, 24, dy);
        ctx.fillStyle = '#000';
        ctx.textAlign = 'right';
        ctx.fillText(v, w - 24, dy);
        ctx.textAlign = 'left';
        dy += 24;
    }
}

// ── KI-67 Analysis text ──
function _renderKi67Analysis(countsByClass) {
    const panel = document.getElementById('viz-tumor');
    panel.innerHTML = '';

    const n0 = countsByClass[0] || 0;
    const pos = (countsByClass[1] || 0) + (countsByClass[2] || 0) + (countsByClass[3] || 0);
    const total = n0 + pos;
    const ki67Index = total === 0 ? 0 : pos / total * 100;
    const interp = ki67Index >= 14 ? 'High' : 'Low';
    const indexColor = ki67Index >= 14 ? '#E84040' : '#2E7D32';

    const row = document.createElement('div');
    row.className = 'viz-chart-row';
    panel.appendChild(row);

    const summary = document.createElement('div');
    summary.className = 'viz-summary';
    panel.appendChild(summary);

    const panelW = panel.clientWidth || 780;
    const cardH = 320;

    const cardW1 = Math.floor(panelW * 0.5 - 8);
    const cv1 = _createHiDPICanvas(cardW1, cardH);
    row.appendChild(cv1);

    const cardW2 = Math.floor(panelW * 0.5 - 8);
    const cv2 = _createHiDPICanvas(cardW2, cardH);
    row.appendChild(cv2);

    _animate(900, (t) => {
        const ease = _easeOutCubic(t);
        const elastic = t < 0.5 ? _easeOutCubic(t * 2) : _easeOutElastic((t - 0.5) * 2) * 0.5 + 0.5;

        const ctx1 = cv1.getContext('2d');
        _drawKi67Card(ctx1, cardW1, cardH, ki67Index, interp, indexColor, pos, n0, total, elastic);

        const ctx2 = cv2.getContext('2d');
        _drawKi67Bars(ctx2, cardW2, cardH, [n0, pos], ease);
    }, () => {
        summary.innerHTML =
            `<strong>KI-67 Labeling Index:</strong> <span style="color:${indexColor};font-weight:700">${ki67Index.toFixed(1)}%</span> ` +
            `&nbsp;|&nbsp; <span style="color:${indexColor};font-weight:700">${interp}</span> ` +
            `&nbsp;|&nbsp; Positive ${pos.toLocaleString()} &nbsp;|&nbsp; Negative ${n0.toLocaleString()} ` +
            `&nbsp;|&nbsp; Total ${total.toLocaleString()}`;
        summary.style.animation = 'fadeIn 0.3s ease';
    });
}

function _drawKi67Card(ctx, w, h, ki67Index, interp, indexColor, pos, neg, total, elastic) {
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;

    ctx.fillStyle = '#000';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('KI-67 Labeling Index', cx, 24);

    ctx.fillStyle = '#666';
    ctx.font = '11px sans-serif';
    ctx.fillText('Positive / Total × 100 (%) — Cutoff: 14%', cx, 42);

    // Big index number
    const cyTs = 130;
    const animVal = ki67Index * elastic;
    ctx.fillStyle = indexColor;
    ctx.font = 'bold 64px sans-serif';
    ctx.fillText(`${animVal.toFixed(1)}%`, cx, cyTs);

    ctx.fillStyle = '#555';
    ctx.font = 'bold 13px sans-serif';
    ctx.fillText(interp, cx, cyTs + 24);

    // Detail rows
    ctx.fillStyle = '#333';
    ctx.font = 'bold 12px sans-serif';
    ctx.textAlign = 'left';
    let dy = 200;
    const items = [
        ['Positive Cells', pos.toLocaleString()],
        ['Negative Cells', neg.toLocaleString()],
        ['Total Cells', total.toLocaleString()],
        ['Cutoff (St Gallen 2013)', '14%'],
    ];
    for (const [k, v] of items) {
        ctx.fillStyle = '#666';
        ctx.fillText(k, 24, dy);
        ctx.fillStyle = '#000';
        ctx.textAlign = 'right';
        ctx.fillText(v, w - 24, dy);
        ctx.textAlign = 'left';
        dy += 24;
    }
}

function _drawKi67Bars(ctx, w, h, counts, ease) {
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;
    ctx.fillStyle = '#000';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Cell Distribution', cx, 24);

    const labels = ['Negative', 'Positive'];
    const colors = ['#27ae60', '#e74c3c'];
    const max = Math.max(1, ...counts);
    const padL = 80, padR = 20, padT = 50, padB = 40;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    const bw = plotW / counts.length * 0.6;
    const gap = plotW / counts.length * 0.4;

    ctx.strokeStyle = '#ddd';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, padT + plotH);
    ctx.lineTo(padL + plotW, padT + plotH);
    ctx.stroke();

    counts.forEach((cnt, i) => {
        const x = padL + i * (bw + gap) + gap / 2;
        const targetH = (cnt / max) * plotH * ease;
        const y = padT + plotH - targetH;
        ctx.fillStyle = colors[i];
        ctx.fillRect(x, y, bw, targetH);

        ctx.fillStyle = '#333';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(labels[i], x + bw / 2, padT + plotH + 18);

        if (targetH > 18) {
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 13px sans-serif';
            ctx.fillText(cnt.toLocaleString(), x + bw / 2, y + targetH / 2 + 5);
        }
    });
}

function _drawHer2Bars(ctx, w, h, counts, ease) {
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;
    ctx.fillStyle = '#000';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Intensity Distribution', cx, 24);

    const labels = ['0+', '1+', '2+', '3+'];
    const max = Math.max(1, ...counts);
    const padL = 50, padR = 20, padT = 50, padB = 40;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    const bw = plotW / counts.length * 0.6;
    const gap = plotW / counts.length * 0.4;

    ctx.strokeStyle = '#ddd';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, padT + plotH);
    ctx.lineTo(padL + plotW, padT + plotH);
    ctx.stroke();

    counts.forEach((cnt, i) => {
        const x = padL + i * (bw + gap) + gap / 2;
        const targetH = (cnt / max) * plotH * ease;
        const y = padT + plotH - targetH;
        ctx.fillStyle = _getColor(i);
        ctx.fillRect(x, y, bw, targetH);

        ctx.fillStyle = '#333';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(labels[i], x + bw / 2, padT + plotH + 18);

        ctx.fillStyle = '#222';
        ctx.font = 'bold 11px sans-serif';
        ctx.fillText(cnt.toLocaleString(), x + bw / 2, y - 4);
    });
}

function _drawScoreCard(ctx, w, h, score, ease, elastic) {
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;

    // text
    ctx.fillStyle = '#000';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`${score.label} Score`, cx, 24);

    ctx.fillStyle = '#666';
    ctx.font = '11px sans-serif';
    ctx.fillText(score.formula, cx, 42);

    // text text text (text)
    const gaugeCy = 140;
    const radius = Math.min(w * 0.35, 95);
    const barColor = _scoreColor(score.value);

    ctx.lineWidth = 14;
    ctx.lineCap = 'round';

    // text text
    ctx.strokeStyle = '#eee';
    ctx.beginPath();
    ctx.arc(cx, gaugeCy, radius, Math.PI, Math.PI * 2);
    ctx.stroke();

    // text
    const animVal = score.value * elastic;
    const angle = Math.PI + Math.PI * (animVal / 100);
    const grad = ctx.createLinearGradient(cx - radius, gaugeCy, cx + radius, gaugeCy);
    grad.addColorStop(0, _lightenColor(barColor, 0.15));
    grad.addColorStop(1, barColor);
    ctx.strokeStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, gaugeCy, radius, Math.PI, angle);
    ctx.stroke();

    // text text
    ctx.fillStyle = barColor;
    ctx.font = 'bold 40px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`${animVal.toFixed(1)}%`, cx, gaugeCy + 8);

    ctx.fillStyle = '#555';
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText(score.label, cx, gaugeCy + 26);

    // text (text)
    if (ease > 0.4) {
        const la = Math.min(1, (ease - 0.4) / 0.4);
        ctx.globalAlpha = la;
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'left';
        let dy = 210;
        for (const d of score.detail) {
            ctx.fillStyle = d.color;
            _roundRect(ctx, 24, dy - 10, 12, 12, 2);
            ctx.fill();
            ctx.fillStyle = '#000';
            ctx.fillText(d.name, 42, dy);
            ctx.textAlign = 'right';
            ctx.fillText(d.value.toLocaleString(), w - 24, dy);
            ctx.textAlign = 'left';
            dy += 22;
        }
        ctx.globalAlpha = 1;
    }
}


// ── Spatial Heatmap text ──
function _renderSpatialHeatmap(cells, countsByClass, segData) {
    const panel = document.getElementById('viz-heatmap');
    panel.innerHTML = '';

    // segmentation text text text + seg overlay text (text text)
    if (segData && segData.overlays && segData.thumbnail) {
        _renderSegHeatmap(panel, segData);
        return;
    }

    // fallback: cell density heatmap
    if (cells.length === 0) { panel.innerHTML = '<p>No cell data</p>'; return; }

    let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
    for (const c of cells) {
        if (c.x < xMin) xMin = c.x; if (c.x > xMax) xMax = c.x;
        if (c.y < yMin) yMin = c.y; if (c.y > yMax) yMax = c.y;
    }
    const rangeW = xMax - xMin || 1, rangeH = yMax - yMin || 1;

    const scroll = document.createElement('div');
    scroll.className = 'viz-heatmap-scroll';

    const activeClasses = Object.entries(countsByClass).filter(([, v]) => v > 0);
    const panels = [{ label: 'All Cells', classId: null }, ...activeClasses.map(([id]) => ({
        label: CLASS_NAMES[parseInt(id)] || `Class ${id}`,
        classId: parseInt(id),
    }))];

    const canvasW = 760, canvasH = Math.max(80, Math.round(760 * rangeH / rangeW));
    const binsX = 100, binsY = Math.max(10, Math.round(binsX * rangeH / rangeW));

    for (const { label, classId } of panels) {
        const titleEl = document.createElement('div');
        titleEl.style.cssText = 'font-weight:700; font-size:14px; padding:4px 0; color:#000;';
        const subset = classId === null ? cells : cells.filter(c => c.class_id === classId);
        titleEl.textContent = `${label}  (n=${subset.length.toLocaleString()})`;
        scroll.appendChild(titleEl);

        const canvas = document.createElement('canvas');
        canvas.width = canvasW;
        canvas.height = Math.min(canvasH, 300);
        scroll.appendChild(canvas);

        _drawHeatmap(canvas, subset, xMin, yMin, rangeW, rangeH, binsX, binsY,
            classId === null ? null : CLASS_COLORS[classId]);
    }

    panel.appendChild(scroll);
}

function _renderStilSpatialHeatmap(panel, score) {
    if (!panel) return;
    panel.innerHTML = '';
    const heatmap = score.spatial_heatmap;
    const cells = heatmap.cells || [];
    const scroll = document.createElement('div');
    scroll.className = 'viz-heatmap-scroll';

    const summary = document.createElement('div');
    summary.className = 'viz-summary';
    summary.innerHTML = `
        <strong>Local sTIL · ${Number(heatmap.grid_size_um || 500)} µm grid</strong><br>
        Global area-weighted sTIL: <strong>${Number(score.score_percent || 0).toFixed(1)}%</strong> ·
        Local maximum: ${Number(heatmap.local_max_percent || 0).toFixed(1)}%<br>
        The global score is calculated from the complete stromal area, not from the hotspot maximum.
    `;
    scroll.appendChild(summary);

    let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
    cells.forEach((cell) => {
        xMin = Math.min(xMin, Number(cell[0]));
        yMin = Math.min(yMin, Number(cell[1]));
        xMax = Math.max(xMax, Number(cell[0]) + Number(cell[2]));
        yMax = Math.max(yMax, Number(cell[1]) + Number(cell[3]));
    });
    const rangeW = Math.max(1, xMax - xMin);
    const rangeH = Math.max(1, yMax - yMin);
    const maxW = 760;
    const maxH = 420;
    const scale = Math.min(maxW / rangeW, maxH / rangeH);
    const canvasW = Math.max(180, Math.round(rangeW * scale));
    const canvasH = Math.max(120, Math.round(rangeH * scale));
    const canvas = _createHiDPICanvas(canvasW, canvasH);
    canvas.style.cssText += '; display:block; margin:12px auto; border:1px solid #d8dce6; border-radius:6px; background:#f7f8fb;';
    scroll.appendChild(canvas);

    const colorForScore = (value) => {
        if (value < 10) return '#2c7bb6';
        if (value < 30) return '#74add1';
        if (value < 50) return '#fdae61';
        return '#d7191c';
    };
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvasW, canvasH);
    const fullGridArea = Math.pow(Number(heatmap.grid_size_um || 500) / 1000, 2);
    cells.forEach((cell) => {
        const x = (Number(cell[0]) - xMin) / rangeW * canvasW;
        const y = (Number(cell[1]) - yMin) / rangeH * canvasH;
        const w = Math.max(1, Number(cell[2]) / rangeW * canvasW);
        const h = Math.max(1, Number(cell[3]) / rangeH * canvasH);
        const coverage = Math.min(1, Number(cell[5] || 0) / Math.max(fullGridArea, 1e-9));
        ctx.globalAlpha = 0.32 + 0.58 * Math.sqrt(coverage);
        ctx.fillStyle = colorForScore(Number(cell[4] || 0));
        ctx.fillRect(x, y, w + 0.5, h + 0.5);
    });
    ctx.globalAlpha = 1;

    const legend = document.createElement('div');
    legend.className = 'stil-heatmap-legend';
    [
        ['0–10%', '#2c7bb6'], ['10–30%', '#74add1'],
        ['30–50%', '#fdae61'], ['≥50%', '#d7191c'],
    ].forEach(([label, color]) => {
        const item = document.createElement('span');
        item.innerHTML = `<i style="background:${color}"></i>${label}`;
        legend.appendChild(item);
    });
    scroll.appendChild(legend);
    panel.appendChild(scroll);
}

/** Segmentation text: text text text text (text text) */
function _renderSegHeatmap(panel, segData) {
    const scroll = document.createElement('div');
    scroll.className = 'viz-heatmap-scroll';

    const modeLabel = document.createElement('div');
    modeLabel.style.cssText = 'font-size:13px; color:#000; font-weight:600; padding:4px 0 8px;';
    modeLabel.textContent = 'Mode: Segmentation probability heatmap';
    scroll.appendChild(modeLabel);

    const thumbSrc = `data:image/jpeg;base64,${segData.thumbnail}`;
    const dispW = Math.min(760, segData.width);
    const dispH = Math.round(dispW * segData.height / segData.width);

    for (const clsName of Object.keys(segData.overlays)) {
        const titleEl = document.createElement('div');
        titleEl.style.cssText = 'font-weight:700; font-size:14px; padding:6px 0 2px; color:#000;';
        titleEl.textContent = clsName;
        scroll.appendChild(titleEl);

        const canvas = _createHiDPICanvas(dispW, dispH);
        canvas.style.cssText += '; border-radius:4px; border:1px solid #ddd; display:block; margin-bottom:8px;';
        scroll.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        const overlaySrc = `data:image/png;base64,${segData.overlays[clsName]}`;

        const thumbImg = new Image();
        const overlayImg = new Image();
        let loaded = 0;
        const onBothLoaded = () => {
            if (++loaded < 2) return;
            ctx.drawImage(thumbImg, 0, 0, dispW, dispH);
            ctx.drawImage(overlayImg, 0, 0, dispW, dispH);
        };
        thumbImg.onload = onBothLoaded;
        overlayImg.onload = onBothLoaded;
        thumbImg.src = thumbSrc;
        overlayImg.src = overlaySrc;
    }

    panel.appendChild(scroll);
}

function _drawHeatmap(canvas, cells, xMin, yMin, rangeW, rangeH, binsX, binsY, baseColor) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = '#e8e8e8';
    ctx.fillRect(0, 0, w, h);

    if (cells.length === 0) {
        ctx.fillStyle = '#999'; ctx.font = '12px sans-serif';
        ctx.textAlign = 'center'; ctx.fillText('No cells', w / 2, h / 2);
        return;
    }

    // histogram2d
    const grid = new Float32Array(binsY * binsX);
    for (const c of cells) {
        const col = Math.min(Math.floor((c.x - xMin) / rangeW * binsX), binsX - 1);
        const row = Math.min(Math.floor((c.y - yMin) / rangeH * binsY), binsY - 1);
        if (col >= 0 && row >= 0) grid[row * binsX + col]++;
    }

    // Gaussian blur (box blur 3 passes)
    const blurred = _blurGrid(grid, binsX, binsY, 3);
    let maxVal = 0;
    for (let i = 0; i < blurred.length; i++) if (blurred[i] > maxVal) maxVal = blurred[i];
    if (maxVal === 0) return;

    // Draw
    const imgData = ctx.createImageData(binsX, binsY);
    const data = imgData.data;
    for (let i = 0; i < blurred.length; i++) {
        const norm = blurred[i] / maxVal;
        if (norm < 0.01) { data[i * 4 + 3] = 0; continue; }
        let r, g, b;
        if (baseColor) {
            const br = parseInt(baseColor.slice(1, 3), 16);
            const bg = parseInt(baseColor.slice(3, 5), 16);
            const bb = parseInt(baseColor.slice(5, 7), 16);
            r = Math.round(br * norm); g = Math.round(bg * norm); b = Math.round(bb * norm);
        } else {
            [r, g, b] = _jetColor(norm);
        }
        data[i * 4] = r; data[i * 4 + 1] = g; data[i * 4 + 2] = b;
        data[i * 4 + 3] = Math.round(norm * 200);
    }

    const offscreen = new OffscreenCanvas(binsX, binsY);
    offscreen.getContext('2d').putImageData(imgData, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(offscreen, 0, 0, w, h);
}

// ── Confidence Distribution text ──
function _renderConfidenceDistribution(confsByClass) {
    const panel = document.getElementById('viz-confidence');
    panel.innerHTML = '';

    const activeClasses = Object.entries(confsByClass).filter(([, v]) => v.length > 0);
    if (activeClasses.length === 0) { panel.innerHTML = '<p>No data</p>'; return; }

    const chartW = 240, chartH = 180;
    const container = document.createElement('div');
    container.style.cssText = `display:flex; flex-wrap:wrap; gap:12px;`;

    for (const [idStr, confs] of activeClasses) {
        const id = parseInt(idStr);
        const canvas = _createHiDPICanvas(chartW, chartH);
        container.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#f8f8f8';
        ctx.fillRect(0, 0, chartW, chartH);

        // Title
        ctx.fillStyle = '#000';
        ctx.font = 'bold 13px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`${CLASS_NAMES[id]} (n=${confs.length.toLocaleString()})`, chartW / 2, 16);

        // Histogram (20 bins, 0~1)
        const nBins = 20;
        const bins = new Float32Array(nBins);
        for (const v of confs) {
            const idx = Math.min(Math.floor(v * nBins), nBins - 1);
            if (idx >= 0) bins[idx]++;
        }
        const maxBin = Math.max(...bins, 1);
        const color = CLASS_COLORS[id] || '#4488CC';
        const plotLeft = 38, plotRight = chartW - 10, plotTop = 26, plotBottom = chartH - 28;
        const plotW = plotRight - plotLeft, plotH = plotBottom - plotTop;
        const binW = plotW / nBins;

        for (let i = 0; i < nBins; i++) {
            const barH = (bins[i] / maxBin) * plotH;
            ctx.fillStyle = color;
            ctx.globalAlpha = 0.85;
            ctx.fillRect(plotLeft + i * binW, plotBottom - barH, binW - 1, barH);
        }
        ctx.globalAlpha = 1;

        // Mean line
        const mean = confs.reduce((a, b) => a + b, 0) / confs.length;
        const meanX = plotLeft + mean * plotW;
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 2]);
        ctx.beginPath();
        ctx.moveTo(meanX, plotTop);
        ctx.lineTo(meanX, plotBottom);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = '#000';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(`avg ${mean.toFixed(2)}`, meanX + 3, plotTop + 12);

        // Axes
        ctx.strokeStyle = '#666';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(plotLeft, plotTop);
        ctx.lineTo(plotLeft, plotBottom);
        ctx.lineTo(plotRight, plotBottom);
        ctx.stroke();

        ctx.fillStyle = '#000';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        for (const v of [0, 0.5, 1]) {
            ctx.fillText(v.toFixed(1), plotLeft + v * plotW, plotBottom + 14);
        }
        ctx.fillText('Confidence', plotLeft + plotW / 2, chartH - 2);
    }

    panel.appendChild(container);
}

// ── Utility ──
function _blurGrid(src, w, h, passes) {
    let a = new Float32Array(src);
    let b = new Float32Array(w * h);
    for (let p = 0; p < passes; p++) {
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const l = x > 0 ? a[y * w + x - 1] : a[y * w + x];
                const c = a[y * w + x];
                const r = x < w - 1 ? a[y * w + x + 1] : a[y * w + x];
                b[y * w + x] = (l + c + r) / 3;
            }
        }
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const t = y > 0 ? b[(y - 1) * w + x] : b[y * w + x];
                const c = b[y * w + x];
                const bt = y < h - 1 ? b[(y + 1) * w + x] : b[y * w + x];
                a[y * w + x] = (t + c + bt) / 3;
            }
        }
    }
    return a;
}

function _jetColor(t) {
    t = Math.max(0, Math.min(1, t));
    let r, g, b;
    if (t < 0.25) { r = 0; g = t * 4; b = 1; }
    else if (t < 0.5) { r = 0; g = 1; b = 1 - (t - 0.25) * 4; }
    else if (t < 0.75) { r = (t - 0.5) * 4; g = 1; b = 0; }
    else { r = 1; g = 1 - (t - 0.75) * 4; b = 0; }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

function _lightenColor(hex, amount) {
    let r = parseInt(hex.slice(1, 3), 16);
    let g = parseInt(hex.slice(3, 5), 16);
    let b = parseInt(hex.slice(5, 7), 16);
    r = Math.min(255, Math.round(r + (255 - r) * amount));
    g = Math.min(255, Math.round(g + (255 - g) * amount));
    b = Math.min(255, Math.round(b + (255 - b) * amount));
    return `rgb(${r},${g},${b})`;
}

function _roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

// ─────────────────────────── PDF EXPORT ───────────────────────────
// text detection_visualization_dialog.pytext PDF text text Canvastext text
// jsPDFtext text import (CDN ESM)

const PDF_W = 2100, PDF_H = 1485;  // text text (text draw text text)
const PDF_SCALE = 2;               // text text text — text text text
const PDF_COL = {
    bg: '#FFFFFF', panel: '#F3F4F6', panelBorder: '#E5E7EB',
    text: '#111827', subtext: '#6B7280', accent: '#1E3A8A',
    tumor: '#DC2626', benign: '#16A34A',
};

async function _exportPDF(state) {
    const { jsPDF } = await import('https://cdn.jsdelivr.net/npm/jspdf@2.5.2/+esm');

    // text text text text text text
    if (state.thumbnailUrl && !state.thumbnailImg) {
        try {
            const img = await _loadImage(state.thumbnailUrl);
            state.thumbnailImg = img;
        } catch (e) { /* text text text text fallback */ }
    }
    const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    const pageW = 297, pageH = 210;

    const str_model_type = state.modelType || 'Quanti HE';
    let list_page_drawers;
    if (str_model_type === 'Quanti PD-L1') {
        list_page_drawers = [
            () => _pdfDrawCover(state),
            () => _pdfDrawClassDist(state),
            () => _pdfDrawPdScoreAnalysis(state),
            () => _pdfDrawConfidence(state),
        ];
    } else if (str_model_type === 'Quanti IHC') {
        const analysisDrawer = (_activeScoreType === 'Allred') ? () => _pdfDrawAllredAnalysis(state)
            : (_activeScoreType === 'KI67') ? () => _pdfDrawKi67Analysis(state)
            : () => _pdfDrawHer2Analysis(state);
        list_page_drawers = [
            () => _pdfDrawCover(state),
            () => _pdfDrawClassDist(state),
            analysisDrawer,
            () => _pdfDrawConfidence(state),
        ];
    } else {
        list_page_drawers = [
            () => _pdfDrawCover(state),
            () => _pdfDrawClassDist(state),
            () => _pdfDrawTumorAnalysis(state),
            () => _pdfDrawSpatialHeatmap(state),
        ];
        if (state.stilScore?.available) {
            list_page_drawers.push(
                () => _pdfDrawStilAnalysis(state),
                () => _pdfDrawStilHeatmap(state),
            );
        }
        list_page_drawers.push(() => _pdfDrawConfidence(state));
    }
    list_page_drawers.forEach((drawPage, i) => {
        const canvas = drawPage();
        if (i > 0) pdf.addPage();
        pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, pageW, pageH);
        canvas.width = 1;
        canvas.height = 1;
    });

    const safeName = (state.slideName || 'slide').replace(/[\\/:*?"<>|]/g, '_');
    const str_model_part = (state.modelType || 'Quanti HE').replace(/[\\/:*?"<>|]/g, '_');
    const str_variant_part = (state.tissue || '').replace(/[\\/:*?"<>|]/g, '_');
    const filename = str_variant_part
        ? `${safeName}_${str_model_part}_${str_variant_part}_report.pdf`
        : `${safeName}_${str_model_part}_report.pdf`;

    // File System Access API text text text text text text
    if (!await window.MediautoSecurity.authorizeExport(filename)) return;
    const blob = pdf.output('blob');
    if (window.showSaveFilePicker) {
        try {
            const handle = await window.showSaveFilePicker({
                suggestedName: filename,
                types: [{ description: 'PDF Document', accept: { 'application/pdf': ['.pdf'] } }],
            });
            const writable = await handle.createWritable();
            await writable.write(blob);
            await writable.close();
            return;
        } catch (e) {
            if (e.name === 'AbortError') return;  // text text
            // text text text text fallback
        }
    }
    // Fallback: text text
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

function _loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('image load failed: ' + src));
        img.src = src;
    });
}

function _pdfNewCanvas() {
    const c = document.createElement('canvas');
    c.width = PDF_W * PDF_SCALE;
    c.height = PDF_H * PDF_SCALE;
    const ctx = c.getContext('2d');
    ctx.scale(PDF_SCALE, PDF_SCALE);
    ctx.fillStyle = PDF_COL.bg;
    ctx.fillRect(0, 0, PDF_W, PDF_H);
    return c;
}

function _pdfPanel(ctx, x, y, w, h) {
    ctx.fillStyle = PDF_COL.panel;
    _roundRect(ctx, x, y, w, h, 16);
    ctx.fill();
    ctx.strokeStyle = PDF_COL.panelBorder;
    ctx.lineWidth = 2;
    ctx.stroke();
}

function _pdfHeader(ctx, title) {
    ctx.fillStyle = PDF_COL.accent;
    ctx.fillRect(0, 0, PDF_W, 130);
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 56px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    ctx.fillText(title, 60, 65);
    ctx.font = '28px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillStyle = '#CBD5E1';
    ctx.fillText(new Date().toLocaleString(), PDF_W - 60, 65);
    // footer
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '20px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'alphabetic';
    ctx.textAlign = 'left';
    ctx.fillText('MeDIAuto Studio · AI Detection Report', 60, PDF_H - 35);
    ctx.textAlign = 'right';
    ctx.fillText('Generated by AI Visualization', PDF_W - 60, PDF_H - 35);
}

function _pdfDrawCover(state) {
    const { cells, countsByClass } = state;
    const str_model_type = state.modelType || 'Quanti HE';
    const str_tissue = state.tissue || '';
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');

    let str_title = 'AI Detection Result Report';
    if (str_model_type === 'Quanti PD-L1') str_title = `PD-L1 Analysis Report (${str_tissue || 'Quanti PD-L1'})`;
    else if (str_model_type === 'Quanti IHC') str_title = `HER2 Analysis Report (${str_tissue || 'Quanti IHC'})`;
    else str_title = `H&E Detection Report (${str_tissue || 'Quanti HE'})`;
    _pdfHeader(ctx, str_title);

    // Top stat panel
    const px = 100, py = 200, pw = PDF_W - 200, ph = 300;
    _pdfPanel(ctx, px, py, pw, ph);

    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '32px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'top';
    ctx.textAlign = 'left';
    ctx.fillText('Total Detected Cells', px + 60, py + 50);
    ctx.fillStyle = PDF_COL.accent;
    ctx.font = 'bold 140px Segoe UI, Arial, sans-serif';
    ctx.fillText(cells.length.toLocaleString(), px + 60, py + 100);

    // Model-specific headline metric
    let str_metric_label = '';
    let str_metric_value = 'N/A';
    let str_metric_color = PDF_COL.subtext;

    if (str_model_type === 'Quanti PD-L1') {
        if (str_tissue === 'Stomach') {
            const int_pos_tumor = countsByClass[3] || 0;
            const int_pos_immune = (countsByClass[4] || 0) + (countsByClass[5] || 0);
            const int_viable_tumor = (countsByClass[0] || 0) + (countsByClass[3] || 0);
            const float_cps = int_viable_tumor === 0 ? null
                : Math.min(100, (int_pos_tumor + int_pos_immune) / int_viable_tumor * 100);
            str_metric_label = 'CPS (Combined Positive Score)';
            if (float_cps !== null) {
                str_metric_value = float_cps.toFixed(1);
                str_metric_color = _scoreColor(float_cps);
            }
        } else {
            const int_neg = countsByClass[0] || 0;
            const int_pos = countsByClass[1] || 0;
            const int_total = int_neg + int_pos;
            const float_tps = int_total === 0 ? null : (int_pos / int_total * 100);
            str_metric_label = 'TPS (Tumor Proportion Score)';
            if (float_tps !== null) {
                str_metric_value = float_tps.toFixed(1) + '%';
                str_metric_color = _scoreColor(float_tps);
            }
        }
    } else if (str_model_type === 'Quanti IHC') {
        const int_n0 = countsByClass[0] || 0;
        const int_n1 = countsByClass[1] || 0;
        const int_n2 = countsByClass[2] || 0;
        const int_n3 = countsByClass[3] || 0;
        const int_total = int_n0 + int_n1 + int_n2 + int_n3;
        if (_activeScoreType === 'Allred') {
            const a = _allredFromCounts(countsByClass);
            str_metric_label = 'Allred Score (PS + IS = TS)';
            if (int_total > 0) {
                str_metric_value = `${a.ts} / 8`;
                str_metric_color = a.ts >= 3 ? '#E84040' : '#2E7D32';
            }
        } else if (_activeScoreType === 'KI67') {
            const int_pos = int_n1 + int_n2 + int_n3;
            const float_ki67 = int_total === 0 ? 0 : int_pos / int_total * 100;
            str_metric_label = 'KI-67 Labeling Index';
            if (int_total > 0) {
                str_metric_value = `${float_ki67.toFixed(1)}%`;
                str_metric_color = float_ki67 >= 14 ? '#E84040' : '#2E7D32';
            }
        } else {
            str_metric_label = 'HER2 Score (dominant / weighted)';
            if (int_total > 0) {
                const float_weighted = (0 * int_n0 + 1 * int_n1 + 2 * int_n2 + 3 * int_n3) / int_total;
                const int_dominant = [int_n0, int_n1, int_n2, int_n3].indexOf(Math.max(int_n0, int_n1, int_n2, int_n3));
                str_metric_value = `${int_dominant}+ / ${float_weighted.toFixed(2)}`;
                str_metric_color = _getColor(Math.round(float_weighted));
            }
        }
    } else {
        // Quanti HE
        if (state.stilScore?.available) {
            str_metric_label = 'AI-estimated stromal TIL';
            str_metric_value = Number(state.stilScore.score_percent || 0).toFixed(1) + '%';
            str_metric_color = '#5147BF';
        } else {
            const int_tumor = countsByClass[6] || 0;
            const int_benign = countsByClass[7] || 0;
            const int_denom = int_tumor + int_benign;
            str_metric_label = 'Tumor Proportion (Tumor / Tumor+Benign)';
            if (int_denom > 0) {
                str_metric_value = (int_tumor / int_denom * 100).toFixed(1) + '%';
                str_metric_color = PDF_COL.tumor;
            }
        }
    }

    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '30px Segoe UI, Arial, sans-serif';
    ctx.fillText(str_metric_label, px + 1050, py + 50);
    ctx.fillStyle = str_metric_color;
    ctx.font = 'bold 130px Segoe UI, Arial, sans-serif';
    ctx.fillText(str_metric_value, px + 1050, py + 105);

    // High-resolution pathology preview
    const tx = 100, ty = 560, tw = 1300, th = 760;
    _pdfPanel(ctx, tx, ty, tw, th);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 32px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Whole-slide Pathology Image', tx + 40, ty + 26);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '22px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(state.slideName || 'slide', tx + tw - 40, ty + 34, 620);

    const coverImg = state.thumbnailImg || null;
    const imageX = tx + 35, imageY = ty + 84, imageW = tw - 70, imageH = th - 119;
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(imageX, imageY, imageW, imageH);
    if (coverImg && coverImg.naturalWidth > 0 && coverImg.naturalHeight > 0) {
        const imageScale = Math.min(imageW / coverImg.naturalWidth, imageH / coverImg.naturalHeight);
        const drawW = coverImg.naturalWidth * imageScale;
        const drawH = coverImg.naturalHeight * imageScale;
        const drawX = imageX + (imageW - drawW) / 2;
        const drawY = imageY + (imageH - drawH) / 2;
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(coverImg, drawX, drawY, drawW, drawH);
    } else {
        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '30px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('Pathology preview unavailable', imageX + imageW / 2, imageY + imageH / 2);
    }
    ctx.strokeStyle = '#D1D5DB';
    ctx.lineWidth = 2;
    ctx.strokeRect(imageX, imageY, imageW, imageH);

    // Compact class breakdown on the right; full distribution remains page 2.
    const bx = 1440, by = 560, bw = 560, bh = 760;
    _pdfPanel(ctx, bx, by, bw, bh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 32px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Detected Classes', bx + 34, by + 26);
    const classIds = Object.keys(countsByClass).map(Number).sort((a, b) => countsByClass[b] - countsByClass[a]);
    const total = cells.length;
    const rowH = Math.min(72, (bh - 105) / Math.max(classIds.length, 1));
    let yy = by + 92;
    for (const id of classIds) {
        const name = CLASS_NAMES[id] || `Class ${id}`;
        const count = countsByClass[id];
        const pct = total > 0 ? (count / total * 100) : 0;

        ctx.fillStyle = CLASS_COLORS[id] || '#888';
        ctx.fillRect(bx + 34, yy + 8, 26, 26);

        ctx.fillStyle = PDF_COL.text;
        ctx.font = '23px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(name, bx + 75, yy + 9, 255);

        ctx.textAlign = 'right';
        ctx.font = 'bold 22px Segoe UI, Arial, sans-serif';
        ctx.fillText(count.toLocaleString(), bx + bw - 34, yy + 8);
        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '20px Segoe UI, Arial, sans-serif';
        ctx.fillText(`${pct.toFixed(1)}%`, bx + bw - 34, yy + 36);

        yy += rowH;
        if (yy > by + bh - 46) break;
    }

    return c;
}

function _pdfDrawClassDist(state) {
    const { countsByClass } = state;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'Class Distribution');

    const ids = Object.keys(countsByClass).map(Number).sort((a, b) => countsByClass[b] - countsByClass[a]);
    const total = ids.reduce((s, i) => s + countsByClass[i], 0);
    if (total === 0) return c;

    // Bar chart left
    const bx = 100, by = 200, bw = 1100, bh = 1170;
    _pdfPanel(ctx, bx, by, bw, bh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 36px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Cell Counts', bx + 40, by + 30);

    const maxCnt = Math.max(...ids.map(i => countsByClass[i]), 1);
    const chartTop = by + 110;
    const chartH = bh - 160;
    const rowH = chartH / Math.max(ids.length, 1);
    const labelW = 320;
    const barX0 = bx + labelW + 20;
    const barMaxW = bx + bw - barX0 - 220;

    for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        const cnt = countsByClass[id];
        const yc = chartTop + i * rowH + rowH * 0.5;
        const bH = rowH * 0.6;

        ctx.fillStyle = PDF_COL.text;
        ctx.font = '28px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText(CLASS_NAMES[id] || `Class ${id}`, barX0 - 15, yc);

        const bW = (cnt / maxCnt) * barMaxW;
        ctx.fillStyle = CLASS_COLORS[id] || '#888';
        ctx.fillRect(barX0, yc - bH / 2, bW, bH);

        ctx.fillStyle = PDF_COL.text;
        ctx.textAlign = 'left';
        ctx.font = 'bold 28px Segoe UI, Arial, sans-serif';
        ctx.fillText(cnt.toLocaleString(), barX0 + bW + 14, yc);
    }

    // Pie chart right
    const px = 1250, py = 200, pw = 750, ph = 1170;
    _pdfPanel(ctx, px, py, pw, ph);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 36px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Proportion', px + 40, py + 30);

    const cx = px + pw / 2, cy = py + 460, R = 300;
    let a0 = -Math.PI / 2;
    for (const id of ids) {
        const frac = countsByClass[id] / total;
        const a1 = a0 + frac * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, R, a0, a1);
        ctx.closePath();
        ctx.fillStyle = CLASS_COLORS[id] || '#888';
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 4;
        ctx.stroke();
        a0 = a1;
    }
    // donut hole
    ctx.fillStyle = PDF_COL.panel;
    ctx.beginPath();
    ctx.arc(cx, cy, R * 0.45, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 40px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total.toLocaleString(), cx, cy - 12);
    ctx.font = '22px Segoe UI, Arial, sans-serif';
    ctx.fillStyle = PDF_COL.subtext;
    ctx.fillText('cells', cx, cy + 24);

    // legend
    let ly = py + 830;
    ctx.font = '24px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        const yy2 = ly + i * 38;
        if (yy2 > py + ph - 30) break;
        ctx.fillStyle = CLASS_COLORS[id] || '#888';
        ctx.fillRect(px + 40, yy2 - 12, 26, 26);
        ctx.fillStyle = PDF_COL.text;
        ctx.textAlign = 'left';
        const pct = (countsByClass[id] / total * 100).toFixed(1);
        ctx.fillText(`${CLASS_NAMES[id] || id}`, px + 78, yy2);
        ctx.fillStyle = PDF_COL.subtext;
        ctx.textAlign = 'right';
        ctx.fillText(`${pct}%`, px + pw - 40, yy2);
    }

    return c;
}

function _pdfDrawTumorAnalysis(state) {
    const { countsByClass } = state;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'Tumor Analysis');

    const tumor = countsByClass[6] || 0;
    const benign = countsByClass[7] || 0;
    const total = tumor + benign;

    // Pie left
    const px = 100, py = 200, pw = 950, ph = 1170;
    _pdfPanel(ctx, px, py, pw, ph);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 36px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Tumor vs Benign Epithelial', px + 40, py + 30);

    if (total === 0) {
        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '40px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('No epithelial cells detected', px + pw / 2, py + ph / 2);
    } else {
        const cx = px + pw / 2, cy = py + 560, R = 360;
        const segs = [
            { name: 'Tumor Epithelial', val: tumor, color: PDF_COL.tumor },
            { name: 'Benign Epithelial', val: benign, color: PDF_COL.benign },
        ];
        let a0 = -Math.PI / 2;
        for (const s of segs) {
            if (s.val === 0) continue;
            const a1 = a0 + (s.val / total) * Math.PI * 2;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.arc(cx, cy, R, a0, a1);
            ctx.closePath();
            ctx.fillStyle = s.color;
            ctx.fill();
            ctx.strokeStyle = '#FFFFFF';
            ctx.lineWidth = 6;
            ctx.stroke();
            a0 = a1;
        }
        // legend
        let ly = py + 1000;
        ctx.font = '28px Segoe UI, Arial, sans-serif';
        ctx.textBaseline = 'middle';
        for (let i = 0; i < segs.length; i++) {
            const s = segs[i];
            const lx = px + 80 + i * 420;
            ctx.fillStyle = s.color;
            ctx.fillRect(lx, ly - 16, 32, 32);
            ctx.fillStyle = PDF_COL.text;
            ctx.textAlign = 'left';
            ctx.fillText(`${s.name}: ${s.val.toLocaleString()}`, lx + 48, ly);
        }
    }

    // Gauge right
    const gx = 1100, gy = 200, gw = 900, gh = 1170;
    _pdfPanel(ctx, gx, gy, gw, gh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 36px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Tumor Proportion Score', gx + 40, gy + 30);

    const ratio = total > 0 ? (tumor / total) : 0;
    const pct = ratio * 100;

    // big number
    ctx.fillStyle = PDF_COL.tumor;
    ctx.font = 'bold 220px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total > 0 ? pct.toFixed(1) + '%' : 'N/A', gx + gw / 2, gy + 380);

    // gauge bar
    const barY = gy + 660, barH = 80;
    const barX = gx + 60, barW = gw - 120;
    _roundRect(ctx, barX, barY, barW, barH, 40);
    ctx.fillStyle = '#E5E7EB';
    ctx.fill();
    if (total > 0) {
        ctx.save();
        _roundRect(ctx, barX, barY, barW, barH, 40);
        ctx.clip();
        const grad = ctx.createLinearGradient(barX, 0, barX + barW, 0);
        grad.addColorStop(0, PDF_COL.benign);
        grad.addColorStop(0.5, '#FBBF24');
        grad.addColorStop(1, PDF_COL.tumor);
        ctx.fillStyle = grad;
        ctx.fillRect(barX, barY, barW * ratio, barH);
        ctx.restore();
        // marker line
        const mx = barX + barW * ratio;
        ctx.strokeStyle = PDF_COL.text;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(mx, barY - 10);
        ctx.lineTo(mx, barY + barH + 10);
        ctx.stroke();
    }
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '24px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('0%', barX, barY + barH + 20);
    ctx.textAlign = 'center';
    ctx.fillText('50%', barX + barW / 2, barY + barH + 20);
    ctx.textAlign = 'right';
    ctx.fillText('100%', barX + barW, barY + barH + 20);

    // counts
    ctx.textAlign = 'left';
    ctx.font = '28px Segoe UI, Arial, sans-serif';
    ctx.fillStyle = PDF_COL.text;
    ctx.fillText(`Tumor:  ${tumor.toLocaleString()}`, gx + 60, gy + 880);
    ctx.fillText(`Benign: ${benign.toLocaleString()}`, gx + 60, gy + 930);
    ctx.fillText(`Total:  ${total.toLocaleString()}`, gx + 60, gy + 980);

    return c;
}

function _pdfDrawPdScoreAnalysis(state) {
    const { countsByClass } = state;
    const str_tissue = state.tissue || 'Stomach';
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, str_tissue === 'Stomach' ? 'PD-L1 Analysis — CPS & TPS' : 'PD-L1 Analysis — TPS');

    const list_scores = [];
    if (str_tissue === 'Stomach') {
        const int_pos_tumor = countsByClass[3] || 0;
        const int_pos_immune = (countsByClass[4] || 0) + (countsByClass[5] || 0);
        const int_viable_tumor = (countsByClass[0] || 0) + (countsByClass[3] || 0);
        const float_cps = int_viable_tumor === 0 ? 0
            : Math.min(100, (int_pos_tumor + int_pos_immune) / int_viable_tumor * 100);
        list_scores.push({
            label: 'CPS',
            value: float_cps,
            unit: '',
            valid: int_viable_tumor > 0,
            formula: '(Pos Tumor + Pos Immune) / Viable Tumor × 100',
            rows: [
                ['Positive Tumor', int_pos_tumor, _getColor(3)],
                ['Positive Immune', int_pos_immune, _getColor(4)],
                ['Viable Tumor', int_viable_tumor, _getColor(0)],
            ],
        });
        const int_neg_epi = countsByClass[0] || 0;
        const int_denom_tps = int_neg_epi + int_pos_tumor;
        const float_tps_stomach = int_denom_tps === 0 ? 0 : int_pos_tumor / int_denom_tps * 100;
        list_scores.push({
            label: 'TPS',
            value: float_tps_stomach,
            unit: '%',
            valid: int_denom_tps > 0,
            formula: 'Pos Epithelial / (Pos + Neg Epithelial) × 100',
            rows: [
                ['Positive Epithelial', int_pos_tumor, _getColor(3)],
                ['Negative Epithelial', int_neg_epi, _getColor(0)],
            ],
        });
    } else {
        const int_neg_tumor = countsByClass[0] || 0;
        const int_pos_tumor = countsByClass[1] || 0;
        const int_total = int_neg_tumor + int_pos_tumor;
        const float_tps = int_total === 0 ? 0 : int_pos_tumor / int_total * 100;
        list_scores.push({
            label: 'TPS',
            value: float_tps,
            unit: '%',
            valid: int_total > 0,
            formula: 'Positive Tumor / (Pos + Neg Tumor) × 100',
            rows: [
                ['Positive Tumor', int_pos_tumor, _getColor(1)],
                ['Negative Tumor', int_neg_tumor, _getColor(0)],
            ],
        });
    }

    const int_card_count = list_scores.length;
    const int_gap = 80;
    const int_card_w = Math.floor((PDF_W - 200 - int_gap * (int_card_count - 1)) / int_card_count);
    const int_card_h = 1170;
    const int_top = 200;

    list_scores.forEach((s, idx) => {
        const int_card_x = 100 + idx * (int_card_w + int_gap);
        _pdfPanel(ctx, int_card_x, int_top, int_card_w, int_card_h);

        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(`${s.label} Score`, int_card_x + 40, int_top + 30);

        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '24px Segoe UI, Arial, sans-serif';
        ctx.fillText(s.formula, int_card_x + 40, int_top + 90);

        // Big number
        const str_value_text = s.valid ? s.value.toFixed(1) + s.unit : 'N/A';
        ctx.fillStyle = s.valid ? _scoreColor(s.value) : PDF_COL.subtext;
        ctx.font = 'bold 220px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(str_value_text, int_card_x + int_card_w / 2, int_top + 320);

        // Gauge bar
        const int_bar_y = int_top + 540, int_bar_h = 70;
        const int_bar_x = int_card_x + 60, int_bar_w = int_card_w - 120;
        _roundRect(ctx, int_bar_x, int_bar_y, int_bar_w, int_bar_h, 35);
        ctx.fillStyle = '#E5E7EB';
        ctx.fill();
        if (s.valid) {
            const float_ratio = Math.max(0, Math.min(1, s.value / 100));
            ctx.save();
            _roundRect(ctx, int_bar_x, int_bar_y, int_bar_w, int_bar_h, 35);
            ctx.clip();
            const grad = ctx.createLinearGradient(int_bar_x, 0, int_bar_x + int_bar_w, 0);
            grad.addColorStop(0, PDF_COL.benign);
            grad.addColorStop(0.5, '#FBBF24');
            grad.addColorStop(1, PDF_COL.tumor);
            ctx.fillStyle = grad;
            ctx.fillRect(int_bar_x, int_bar_y, int_bar_w * float_ratio, int_bar_h);
            ctx.restore();
        }
        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '22px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText('0', int_bar_x, int_bar_y + int_bar_h + 14);
        ctx.textAlign = 'center';
        ctx.fillText('50', int_bar_x + int_bar_w / 2, int_bar_y + int_bar_h + 14);
        ctx.textAlign = 'right';
        ctx.fillText('100', int_bar_x + int_bar_w, int_bar_y + int_bar_h + 14);

        // Breakdown rows
        let int_row_y = int_top + 720;
        ctx.font = '28px Segoe UI, Arial, sans-serif';
        ctx.textBaseline = 'middle';
        for (const [name, val, color] of s.rows) {
            ctx.fillStyle = color;
            ctx.fillRect(int_card_x + 60, int_row_y - 16, 32, 32);
            ctx.fillStyle = PDF_COL.text;
            ctx.textAlign = 'left';
            ctx.fillText(name, int_card_x + 110, int_row_y);
            ctx.textAlign = 'right';
            ctx.font = 'bold 28px Segoe UI, Arial, sans-serif';
            ctx.fillText(val.toLocaleString(), int_card_x + int_card_w - 60, int_row_y);
            ctx.font = '28px Segoe UI, Arial, sans-serif';
            int_row_y += 58;
        }
    });

    return c;
}

function _pdfDrawHer2Analysis(state) {
    const { countsByClass } = state;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'HER2 Analysis');

    const int_n0 = countsByClass[0] || 0;
    const int_n1 = countsByClass[1] || 0;
    const int_n2 = countsByClass[2] || 0;
    const int_n3 = countsByClass[3] || 0;
    const list_bins = [int_n0, int_n1, int_n2, int_n3];
    const int_total = int_n0 + int_n1 + int_n2 + int_n3;
    const float_weighted = int_total === 0 ? 0
        : (0 * int_n0 + 1 * int_n1 + 2 * int_n2 + 3 * int_n3) / int_total;
    const int_dominant = int_total === 0 ? 0 : list_bins.indexOf(Math.max(...list_bins));
    const str_bar_color = _getColor(Math.round(float_weighted));

    // Left card — HER2 gauge
    const gx = 100, gy = 200, gw = 950, gh = 1170;
    _pdfPanel(ctx, gx, gy, gw, gh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('HER2 Score', gx + 40, gy + 30);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '24px Segoe UI, Arial, sans-serif';
    ctx.fillText('Weighted mean of intensity (0+ / 1+ / 2+ / 3+)', gx + 40, gy + 90);

    // Dominant big label
    ctx.fillStyle = int_total > 0 ? str_bar_color : PDF_COL.subtext;
    ctx.font = 'bold 260px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(int_total > 0 ? `${int_dominant}+` : 'N/A', gx + gw / 2, gy + 380);

    ctx.fillStyle = PDF_COL.text;
    ctx.font = '32px Segoe UI, Arial, sans-serif';
    ctx.fillText(int_total > 0 ? `weighted mean ${float_weighted.toFixed(2)}` : '—', gx + gw / 2, gy + 560);

    // 0~3 gauge bar
    const int_bar_y = gy + 700, int_bar_h = 80;
    const int_bar_x = gx + 60, int_bar_w = gw - 120;
    _roundRect(ctx, int_bar_x, int_bar_y, int_bar_w, int_bar_h, 40);
    ctx.fillStyle = '#E5E7EB';
    ctx.fill();
    if (int_total > 0) {
        ctx.save();
        _roundRect(ctx, int_bar_x, int_bar_y, int_bar_w, int_bar_h, 40);
        ctx.clip();
        const grad = ctx.createLinearGradient(int_bar_x, 0, int_bar_x + int_bar_w, 0);
        grad.addColorStop(0, _getColor(0));
        grad.addColorStop(1 / 3, _getColor(1));
        grad.addColorStop(2 / 3, _getColor(2));
        grad.addColorStop(1, _getColor(3));
        ctx.fillStyle = grad;
        ctx.fillRect(int_bar_x, int_bar_y, int_bar_w * (float_weighted / 3), int_bar_h);
        ctx.restore();
        const int_marker = int_bar_x + int_bar_w * (float_weighted / 3);
        ctx.strokeStyle = PDF_COL.text;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(int_marker, int_bar_y - 10);
        ctx.lineTo(int_marker, int_bar_y + int_bar_h + 10);
        ctx.stroke();
    }
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '22px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'top';
    ['0+', '1+', '2+', '3+'].forEach((lbl, i) => {
        ctx.textAlign = i === 0 ? 'left' : (i === 3 ? 'right' : 'center');
        const int_lx = int_bar_x + (int_bar_w * i / 3);
        ctx.fillText(lbl, int_lx, int_bar_y + int_bar_h + 14);
    });

    ctx.fillStyle = PDF_COL.text;
    ctx.font = '28px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`Total: ${int_total.toLocaleString()}`, gx + 60, gy + 920);

    // Right card — intensity distribution bars
    const bx = 1100, by = 200, bw = 900, bh = 1170;
    _pdfPanel(ctx, bx, by, bw, bh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Intensity Distribution', bx + 40, by + 30);

    const int_max = Math.max(...list_bins, 1);
    const int_chart_x = bx + 160;
    const int_chart_y = by + 150;
    const int_chart_w = bw - 240;
    const int_chart_h = bh - 260;
    const int_row_h = int_chart_h / 4;

    ['0+', '1+', '2+', '3+'].forEach((lbl, i) => {
        const int_yc = int_chart_y + i * int_row_h + int_row_h / 2;
        const int_bar_local_h = Math.min(int_row_h * 0.6, 90);
        const int_local_w = (list_bins[i] / int_max) * int_chart_w;

        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 32px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText(lbl, int_chart_x - 20, int_yc);

        ctx.fillStyle = _getColor(i);
        ctx.fillRect(int_chart_x, int_yc - int_bar_local_h / 2, int_local_w, int_bar_local_h);

        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 28px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        const int_pct = int_total > 0 ? (list_bins[i] / int_total * 100) : 0;
        ctx.fillText(
            `${list_bins[i].toLocaleString()} (${int_pct.toFixed(1)}%)`,
            int_chart_x + int_local_w + 14, int_yc
        );
    });

    return c;
}

function _pdfDrawAllredAnalysis(state) {
    const { countsByClass } = state;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'Allred Analysis');

    const a = _allredFromCounts(countsByClass);
    const list_bins = [a.n0, a.n1, a.n2, a.n3];
    const str_ts_color = a.ts >= 3 ? '#E84040' : '#2E7D32';

    // Left card — Allred score summary
    const gx = 100, gy = 200, gw = 950, gh = 1170;
    _pdfPanel(ctx, gx, gy, gw, gh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Allred Score', gx + 40, gy + 30);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '24px Segoe UI, Arial, sans-serif';
    ctx.fillText('Proportion (0-5) + Intensity (0-3) = Total (0-8)', gx + 40, gy + 90);

    // Big TS label
    ctx.fillStyle = a.total > 0 ? str_ts_color : PDF_COL.subtext;
    ctx.font = 'bold 260px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(a.total > 0 ? `${a.ts}` : 'N/A', gx + gw / 2, gy + 380);

    ctx.fillStyle = PDF_COL.text;
    ctx.font = '32px Segoe UI, Arial, sans-serif';
    ctx.fillText(a.total > 0 ? `/ 8    ${a.interpretation}` : '—', gx + gw / 2, gy + 560);

    // Stat rows: PS / IS / TS / Positive% / Avg intensity
    const int_stat_x = gx + 60;
    let int_stat_y = gy + 700;
    const int_row_h = 62;
    const list_rows = [
        ['Proportion Score (PS)', `${a.ps}  (${a.posPct.toFixed(1)}% positive)`],
        ['Intensity Score (IS)', `${a.is_}  (avg ${a.avg.toFixed(2)})`],
        ['Total Score (TS)', `${a.ts}  (${a.interpretation})`],
        ['Positive Cells', `${a.pos.toLocaleString()} / ${a.total.toLocaleString()}`],
    ];
    ctx.font = '28px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'middle';
    for (const [k, v] of list_rows) {
        ctx.fillStyle = PDF_COL.subtext;
        ctx.textAlign = 'left';
        ctx.fillText(k, int_stat_x, int_stat_y);
        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 28px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(v, gx + gw - 60, int_stat_y);
        ctx.font = '28px Segoe UI, Arial, sans-serif';
        int_stat_y += int_row_h;
    }

    // Right card — intensity distribution bars
    const bx = 1100, by = 200, bw = 900, bh = 1170;
    _pdfPanel(ctx, bx, by, bw, bh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Intensity Distribution', bx + 40, by + 30);

    const int_max = Math.max(...list_bins, 1);
    const int_chart_x = bx + 160;
    const int_chart_y = by + 150;
    const int_chart_w = bw - 240;
    const int_chart_h = bh - 260;
    const int_bar_row_h = int_chart_h / 4;

    ['0+', '1+', '2+', '3+'].forEach((lbl, i) => {
        const int_yc = int_chart_y + i * int_bar_row_h + int_bar_row_h / 2;
        const int_bar_local_h = Math.min(int_bar_row_h * 0.6, 90);
        const int_local_w = (list_bins[i] / int_max) * int_chart_w;

        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 32px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText(lbl, int_chart_x - 20, int_yc);

        ctx.fillStyle = _getColor(i);
        ctx.fillRect(int_chart_x, int_yc - int_bar_local_h / 2, int_local_w, int_bar_local_h);

        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 28px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        const int_pct = a.total > 0 ? (list_bins[i] / a.total * 100) : 0;
        ctx.fillText(
            `${list_bins[i].toLocaleString()} (${int_pct.toFixed(1)}%)`,
            int_chart_x + int_local_w + 14, int_yc
        );
    });

    return c;
}

function _pdfDrawKi67Analysis(state) {
    const { countsByClass } = state;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'KI-67 Analysis');

    const n0 = countsByClass[0] || 0;
    const pos = (countsByClass[1] || 0) + (countsByClass[2] || 0) + (countsByClass[3] || 0);
    const total = n0 + pos;
    const ki67Index = total === 0 ? 0 : pos / total * 100;
    const interp = ki67Index >= 14 ? 'High' : 'Low';
    const indexColor = ki67Index >= 14 ? '#E84040' : '#2E7D32';

    // Left card — KI-67 score summary
    const gx = 100, gy = 200, gw = 950, gh = 1170;
    _pdfPanel(ctx, gx, gy, gw, gh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('KI-67 Labeling Index', gx + 40, gy + 30);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '24px Segoe UI, Arial, sans-serif';
    ctx.fillText('Positive / Total × 100 (%) — Cutoff: 14% (St Gallen 2013)', gx + 40, gy + 90);

    // Big index number
    ctx.fillStyle = total > 0 ? indexColor : PDF_COL.subtext;
    ctx.font = 'bold 220px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total > 0 ? `${ki67Index.toFixed(1)}%` : 'N/A', gx + gw / 2, gy + 380);

    ctx.fillStyle = PDF_COL.text;
    ctx.font = '32px Segoe UI, Arial, sans-serif';
    ctx.fillText(total > 0 ? interp : '—', gx + gw / 2, gy + 560);

    // Stat rows
    const statX = gx + 60;
    let statY = gy + 700;
    const rowH = 62;
    const rows = [
        ['Positive Cells', pos.toLocaleString()],
        ['Negative Cells', n0.toLocaleString()],
        ['Total Cells', total.toLocaleString()],
        ['Cutoff', '14% (St Gallen 2013)'],
    ];
    ctx.font = '28px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'middle';
    for (const [k, v] of rows) {
        ctx.fillStyle = PDF_COL.subtext;
        ctx.textAlign = 'left';
        ctx.fillText(k, statX, statY);
        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 28px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(v, gx + gw - 60, statY);
        ctx.font = '28px Segoe UI, Arial, sans-serif';
        statY += rowH;
    }

    // Right card — Negative vs Positive bars
    const bx = 1100, by = 200, bw = 900, bh = 1170;
    _pdfPanel(ctx, bx, by, bw, bh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 44px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Cell Distribution', bx + 40, by + 30);

    const bins = [n0, pos];
    const labels = ['Negative', 'Positive'];
    const colors = ['#27ae60', '#e74c3c'];
    const maxBin = Math.max(...bins, 1);
    const chartX = bx + 200;
    const chartY = by + 200;
    const chartW = bw - 300;
    const chartH = bh - 360;
    const barRowH = chartH / 2;

    labels.forEach((lbl, i) => {
        const yc = chartY + i * barRowH + barRowH / 2;
        const barH = Math.min(barRowH * 0.6, 120);
        const localW = (bins[i] / maxBin) * chartW;

        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 32px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        ctx.fillText(lbl, chartX - 20, yc);

        ctx.fillStyle = colors[i];
        ctx.fillRect(chartX, yc - barH / 2, localW, barH);

        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 28px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        const pct = total > 0 ? (bins[i] / total * 100) : 0;
        ctx.fillText(
            `${bins[i].toLocaleString()} (${pct.toFixed(1)}%)`,
            chartX + localW + 14, yc
        );
    });

    return c;
}

function _pdfDrawSpatialHeatmap(state) {
    const { cells, countsByClass, thumbnailImg, slideDims } = state;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'Spatial Distribution');

    if (cells.length === 0) return c;

    // text text WSI level-0 text. text level-0 text text text
    // text/text text text text.
    let originX = 0, originY = 0, slideW, slideH;
    if (slideDims && slideDims[0] && slideDims[1]) {
        slideW = slideDims[0];
        slideH = slideDims[1];
    } else {
        // text: text bbox
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const cell of cells) {
            if (cell.x < minX) minX = cell.x;
            if (cell.x > maxX) maxX = cell.x;
            if (cell.y < minY) minY = cell.y;
            if (cell.y > maxY) maxY = cell.y;
        }
        originX = minX; originY = minY;
        slideW = Math.max(maxX - minX, 1);
        slideH = Math.max(maxY - minY, 1);
    }

    // plot panel
    const px = 100, py = 200, pw = 1500, ph = 1170;
    _pdfPanel(ctx, px, py, pw, ph);

    const padding = 60;
    const innerW = pw - padding * 2;
    const innerH = ph - padding * 2;
    const scale = Math.min(innerW / slideW, innerH / slideH);
    const drawW = slideW * scale;
    const drawH = slideH * scale;
    const ox = px + (pw - drawW) / 2;
    const oy = py + (ph - drawH) / 2;

    // text text text (text)
    if (thumbnailImg) {
        ctx.drawImage(thumbnailImg, ox, oy, drawW, drawH);
    } else {
        ctx.fillStyle = '#FAFAFA';
        ctx.fillRect(ox, oy, drawW, drawH);
    }
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 2;
    ctx.strokeRect(ox, oy, drawW, drawH);

    // text text text text text text (text text text text)
    if (thumbnailImg) {
        ctx.fillStyle = 'rgba(255,255,255,0.20)';
        ctx.fillRect(ox, oy, drawW, drawH);
    }

    // text text (text) — text text text text text
    const MAX_PTS = 80000;
    const step = cells.length > MAX_PTS ? Math.ceil(cells.length / MAX_PTS) : 1;
    const dotR = Math.max(1.5, Math.min(drawW, drawH) / 600);
    ctx.globalAlpha = 0.85;
    for (let i = 0; i < cells.length; i += step) {
        const cell = cells[i];
        const sx = ox + ((cell.x - originX) / slideW) * drawW;
        const sy = oy + ((cell.y - originY) / slideH) * drawH;
        ctx.fillStyle = CLASS_COLORS[cell.class_id] || '#888';
        ctx.beginPath();
        ctx.arc(sx, sy, dotR, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1;

    // legend right
    const lx = 1660, ly = 220, lw = 360, lh = 1150;
    _pdfPanel(ctx, lx, ly, lw, lh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 32px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Legend', lx + 24, ly + 24);

    let yy = ly + 90;
    ctx.font = '24px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'middle';
    const ids = Object.keys(countsByClass).map(Number).sort((a, b) => countsByClass[b] - countsByClass[a]);
    for (const id of ids) {
        ctx.fillStyle = CLASS_COLORS[id] || '#888';
        ctx.fillRect(lx + 24, yy - 12, 26, 26);
        ctx.fillStyle = PDF_COL.text;
        ctx.textAlign = 'left';
        ctx.fillText(`${CLASS_NAMES[id] || id}`, lx + 60, yy);
        ctx.fillStyle = PDF_COL.subtext;
        ctx.textAlign = 'right';
        ctx.fillText(countsByClass[id].toLocaleString(), lx + lw - 24, yy);
        yy += 44;
    }
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '20px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`Total: ${cells.length.toLocaleString()}`, lx + 24, yy + 20);
    if (step > 1) {
        ctx.fillText(`(showing 1/${step} for clarity)`, lx + 24, yy + 50);
    }

    return c;
}

function _pdfDrawStilAnalysis(state) {
    const score = state.stilScore || {};
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'AI-estimated sTIL Analysis');

    const sx = 100, sy = 200, sw = 760, sh = 1170;
    _pdfPanel(ctx, sx, sy, sw, sh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 40px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Global stromal TIL', sx + 45, sy + 40);

    ctx.fillStyle = '#5147BF';
    ctx.font = 'bold 210px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${Number(score.score_percent || 0).toFixed(1)}%`, sx + sw / 2, sy + 330);

    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '27px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Area-weighted across analyzed', sx + sw / 2, sy + 485);
    ctx.fillText('tumor-associated stroma', sx + sw / 2, sy + 525);

    const formulaY = sy + 620;
    ctx.fillStyle = '#EEF0FF';
    _roundRect(ctx, sx + 45, formulaY, sw - 90, 150, 14);
    ctx.fill();
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 26px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Calibrated immune-cell area', sx + sw / 2, formulaY + 45);
    ctx.font = '24px Segoe UI, Arial, sans-serif';
    ctx.fillText('÷ tumor-associated stroma area × 100', sx + sw / 2, formulaY + 92);

    const noticeY = sy + 880;
    ctx.fillStyle = '#F6F7FA';
    _roundRect(ctx, sx + 45, noticeY, sw - 90, 190, 14);
    ctx.fill();
    ctx.strokeStyle = '#D7DAE3';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 25px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Research-use estimate', sx + 75, noticeY + 30);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '22px Segoe UI, Arial, sans-serif';
    ctx.fillText('Not clinically validated.', sx + 75, noticeY + 76);
    ctx.fillText('Pathologist calibration is required.', sx + 75, noticeY + 112);

    const mx = 910, my = 200, mw = 1090, mh = 1170;
    _pdfPanel(ctx, mx, my, mw, mh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 40px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Quantitative Results', mx + 45, my + 40);

    const metrics = [
        ['Lymphocyte density', `${Number(score.lymphocyte_density_cells_mm2 || 0).toLocaleString()} cells/mm²`],
        ['Plasma-cell density', `${Number(score.plasma_density_cells_mm2 || 0).toLocaleString()} cells/mm²`],
        ['Combined immune density', `${Number(score.immune_density_cells_mm2 || 0).toLocaleString()} cells/mm²`],
        ['Tumor-associated stroma', `${Number(score.tumor_associated_stroma_area_mm2 || 0).toFixed(2)} mm²`],
        ['Segmented tumor area', `${Number(score.segmented_tumor_area_mm2 || 0).toFixed(2)} mm²`],
        ['Lymphocytes in TAS', Number(score.lymphocyte_count || 0).toLocaleString()],
        ['Plasma cells in TAS', Number(score.plasma_count || 0).toLocaleString()],
        ['Immune-area coefficient', `${Number(score.immune_cell_area_um2 || 0).toFixed(2)} µm²/cell`],
    ];
    let rowY = my + 135;
    metrics.forEach(([label, value], index) => {
        if (index % 2 === 0) {
            ctx.fillStyle = '#F8F9FB';
            ctx.fillRect(mx + 35, rowY - 17, mw - 70, 82);
        }
        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '25px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, mx + 55, rowY + 22);
        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 27px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(value, mx + mw - 55, rowY + 22);
        rowY += 86;
    });

    const methodY = my + 885;
    ctx.strokeStyle = PDF_COL.panelBorder;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(mx + 45, methodY);
    ctx.lineTo(mx + mw - 45, methodY);
    ctx.stroke();
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 25px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Method settings', mx + 50, methodY + 30);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '22px Segoe UI, Arial, sans-serif';
    ctx.fillText(`Detection confidence ≥ ${Number(score.minimum_detection_confidence || 0).toFixed(2)}`, mx + 50, methodY + 78);
    ctx.fillText(`Tumor proximity approximation: ${Number(score.tumor_proximity_um || 0).toFixed(0)} µm`, mx + 50, methodY + 116);
    ctx.fillText('Current model does not separately exclude in-situ tumor,', mx + 50, methodY + 164);
    ctx.fillText('necrosis, or healthy glands.', mx + 50, methodY + 198);

    return c;
}

function _pdfDrawStilHeatmap(state) {
    const score = state.stilScore || {};
    const heatmap = score.spatial_heatmap || {};
    const cells = Array.isArray(heatmap.cells) ? heatmap.cells : [];
    const thumbnailImg = state.thumbnailImg || null;
    const slideDims = state.slideDims || null;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'Local sTIL Heatmap');

    const px = 100, py = 200, pw = 1510, ph = 1170;
    _pdfPanel(ctx, px, py, pw, ph);
    if (cells.length === 0) {
        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '40px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('No local sTIL grid data', px + pw / 2, py + ph / 2);
    } else {
        const hasSlideDimensions = Number(slideDims?.[0]) > 0 && Number(slideDims?.[1]) > 0;
        let originX = 0;
        let originY = 0;
        let rangeW = hasSlideDimensions ? Number(slideDims[0]) : 0;
        let rangeH = hasSlideDimensions ? Number(slideDims[1]) : 0;

        // Older cached results may not carry level-0 slide dimensions. Keep a
        // safe grid-only fallback for those reports instead of misaligning the
        // whole-slide thumbnail with a heatmap bounding box.
        if (!hasSlideDimensions) {
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            cells.forEach((cell) => {
                minX = Math.min(minX, Number(cell[0]));
                minY = Math.min(minY, Number(cell[1]));
                maxX = Math.max(maxX, Number(cell[0]) + Number(cell[2]));
                maxY = Math.max(maxY, Number(cell[1]) + Number(cell[3]));
            });
            originX = minX;
            originY = minY;
            rangeW = Math.max(1, maxX - minX);
            rangeH = Math.max(1, maxY - minY);
        }

        const pad = 55;
        const scale = Math.min((pw - pad * 2) / rangeW, (ph - pad * 2) / rangeH);
        const drawW = rangeW * scale;
        const drawH = rangeH * scale;
        const ox = px + (pw - drawW) / 2;
        const oy = py + (ph - drawH) / 2;

        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(ox, oy, drawW, drawH);
        if (hasSlideDimensions && thumbnailImg) {
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = 'high';
            ctx.drawImage(thumbnailImg, ox, oy, drawW, drawH);
            // A very light veil keeps the overlay readable while preserving
            // the underlying pathology morphology.
            ctx.fillStyle = 'rgba(255,255,255,0.08)';
            ctx.fillRect(ox, oy, drawW, drawH);
        }

        const gridSizeMm = Number(heatmap.grid_size_um || 500) / 1000;
        const fullGridAreaMm2 = Math.max(1e-9, gridSizeMm * gridSizeMm);
        const colorForScore = (value) => {
            if (value < 10) return '#2C7BB6';
            if (value < 30) return '#74ADD1';
            if (value < 50) return '#FDAE61';
            return '#D7191C';
        };
        cells.forEach((cell) => {
            const x = ox + (Number(cell[0]) - originX) * scale;
            const y = oy + (Number(cell[1]) - originY) * scale;
            const w = Math.max(1, Number(cell[2]) * scale);
            const h = Math.max(1, Number(cell[3]) * scale);
            const coverage = Math.min(1, Number(cell[5] || 0) / fullGridAreaMm2);
            ctx.globalAlpha = hasSlideDimensions && thumbnailImg
                ? 0.30 + 0.32 * Math.sqrt(coverage)
                : 0.38 + 0.55 * Math.sqrt(coverage);
            ctx.fillStyle = colorForScore(Number(cell[4] || 0));
            ctx.fillRect(x, y, w + 0.5, h + 0.5);
        });
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#64748B';
        ctx.lineWidth = 2;
        ctx.strokeRect(ox, oy, drawW, drawH);
    }

    const lx = 1660, ly = 200, lw = 340, lh = 1170;
    _pdfPanel(ctx, lx, ly, lw, lh);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 30px Segoe UI, Arial, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('Local sTIL', lx + 28, ly + 30);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '22px Segoe UI, Arial, sans-serif';
    ctx.fillText(`${Number(heatmap.grid_size_um || 500)} µm grid`, lx + 28, ly + 78);

    ctx.fillStyle = '#5147BF';
    ctx.font = 'bold 68px Segoe UI, Arial, sans-serif';
    ctx.fillText(`${Number(score.score_percent || 0).toFixed(1)}%`, lx + 28, ly + 145);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '21px Segoe UI, Arial, sans-serif';
    ctx.fillText('Global area-weighted', lx + 28, ly + 225);
    ctx.fillStyle = PDF_COL.text;
    ctx.font = 'bold 30px Segoe UI, Arial, sans-serif';
    ctx.fillText(`${Number(heatmap.local_max_percent || 0).toFixed(1)}%`, lx + 28, ly + 285);
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '21px Segoe UI, Arial, sans-serif';
    ctx.fillText('Local maximum', lx + 28, ly + 326);

    const legend = [
        ['0–10%', '#2C7BB6'], ['10–30%', '#74ADD1'],
        ['30–50%', '#FDAE61'], ['≥50%', '#D7191C'],
    ];
    let yy = ly + 430;
    ctx.font = '23px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'middle';
    legend.forEach(([label, color]) => {
        ctx.fillStyle = color;
        ctx.fillRect(lx + 28, yy - 15, 34, 30);
        ctx.fillStyle = PDF_COL.text;
        ctx.fillText(label, lx + 80, yy);
        yy += 58;
    });

    ctx.strokeStyle = PDF_COL.panelBorder;
    ctx.beginPath();
    ctx.moveTo(lx + 28, yy + 15);
    ctx.lineTo(lx + lw - 28, yy + 15);
    ctx.stroke();
    ctx.fillStyle = PDF_COL.subtext;
    ctx.font = '20px Segoe UI, Arial, sans-serif';
    ctx.textBaseline = 'top';
    ctx.fillText('Global score uses the', lx + 28, yy + 50);
    ctx.fillText('complete analyzed stromal', lx + 28, yy + 82);
    ctx.fillText('area, not the hotspot.', lx + 28, yy + 114);
    ctx.fillText(`${cells.length.toLocaleString()} TAS grid cells`, lx + 28, yy + 176);
    ctx.fillText('Research-use estimate', lx + 28, yy + 238);
    ctx.fillText('Not clinically validated', lx + 28, yy + 270);

    return c;
}

function _pdfDrawConfidence(state) {
    const { confsByClass } = state;
    const c = _pdfNewCanvas();
    const ctx = c.getContext('2d');
    _pdfHeader(ctx, 'Confidence Distribution');

    const ids = Object.keys(confsByClass).map(Number).sort((a, b) => a - b);
    if (ids.length === 0) return c;

    const cols = Math.min(ids.length, 3);
    const rows = Math.ceil(ids.length / cols);
    const gridX = 100, gridY = 200;
    const gridW = PDF_W - 200, gridH = 1170;
    const cellW = gridW / cols;
    const cellH = gridH / rows;

    const BINS = 20;

    for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        const col = i % cols, row = Math.floor(i / cols);
        const x = gridX + col * cellW + 20;
        const y = gridY + row * cellH + 20;
        const w = cellW - 40;
        const h = cellH - 40;
        _pdfPanel(ctx, x, y, w, h);

        ctx.fillStyle = CLASS_COLORS[id] || '#888';
        ctx.fillRect(x + 24, y + 28, 28, 28);
        ctx.fillStyle = PDF_COL.text;
        ctx.font = 'bold 26px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(`${CLASS_NAMES[id] || id}  (n=${confsByClass[id].length})`, x + 62, y + 28);

        const confs = confsByClass[id];
        const bins = new Array(BINS).fill(0);
        for (const v of confs) {
            const b = Math.min(BINS - 1, Math.max(0, Math.floor(v * BINS)));
            bins[b]++;
        }
        const maxBin = Math.max(...bins, 1);
        const chartX = x + 70, chartY = y + 90;
        const chartW = w - 100, chartH = h - 160;

        // axes
        ctx.strokeStyle = PDF_COL.subtext;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(chartX, chartY);
        ctx.lineTo(chartX, chartY + chartH);
        ctx.lineTo(chartX + chartW, chartY + chartH);
        ctx.stroke();

        const bw = chartW / BINS;
        ctx.fillStyle = CLASS_COLORS[id] || '#888';
        for (let b = 0; b < BINS; b++) {
            const bh = (bins[b] / maxBin) * chartH * 0.92;
            ctx.fillRect(chartX + b * bw + 1, chartY + chartH - bh, bw - 2, bh);
        }

        // x labels
        ctx.fillStyle = PDF_COL.subtext;
        ctx.font = '18px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText('0.0', chartX, chartY + chartH + 8);
        ctx.fillText('0.5', chartX + chartW / 2, chartY + chartH + 8);
        ctx.fillText('1.0', chartX + chartW, chartY + chartH + 8);

        // mean line
        const mean = confs.reduce((s, v) => s + v, 0) / confs.length;
        const mx = chartX + mean * chartW;
        ctx.strokeStyle = PDF_COL.tumor;
        ctx.setLineDash([6, 4]);
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(mx, chartY);
        ctx.lineTo(mx, chartY + chartH);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = PDF_COL.tumor;
        ctx.font = 'bold 20px Segoe UI, Arial, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(`μ=${mean.toFixed(2)}`, mx + 6, chartY + 4);
    }

    return c;
}
