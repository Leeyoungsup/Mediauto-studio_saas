import { PatchGridLayer } from './patch-grid-layer.js?v=20260527-08';
import { PatchStatusLayer } from './patch-status-layer.js?v=20260527-03';
import { WsiRequiredRegionLayer } from './wsi-required-region-layer.js?v=20260526-06';
import { CellAnnotationEditor } from './cell-annotation-editor.js?v=20260527-01';

class PatchFocusLayer {
    constructor() {
        this.patch = null;
        this.visible = false;
    }

    setPatch(patch) {
        this.patch = patch || null;
        this.visible = Boolean(patch);
    }

    clear() {
        this.patch = null;
        this.visible = false;
    }

    draw(ctx, viewer) {
        if (!this.visible || !this.patch || !viewer?.slideInfo) return;
        const x = Number(this.patch.x ?? this.patch.int_x ?? 0);
        const y = Number(this.patch.y ?? this.patch.int_y ?? 0);
        const w = Number(this.patch.w ?? this.patch.int_w ?? 0);
        const h = Number(this.patch.h ?? this.patch.int_h ?? 0);
        if (w <= 0 || h <= 0) return;
        const [cx, cy] = viewer.sceneToCanvas(x, y);
        const cw = w * viewer.zoom;
        const ch = h * viewer.zoom;
        ctx.save();
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.rect(0, 0, viewer._viewW, viewer._viewH);
        ctx.rect(cx, cy, cw, ch);
        ctx.fill('evenodd');
        ctx.strokeStyle = '#6c5ce7';
        ctx.lineWidth = 2;
        ctx.strokeRect(cx, cy, cw, ch);
        ctx.restore();
    }
}

export class CellPatchWorkflow {
    constructor({ api, viewer, canvas, setStatus, onRequiredRegionSaved } = {}) {
        this.api = api;
        this.viewer = viewer;
        this.canvas = canvas;
        this.setStatus = setStatus || (() => {});
        this.onRequiredRegionSaved = onRequiredRegionSaved || (() => {});
        this.slideId = '';
        this.grid = new PatchGridLayer();
        this.status = new PatchStatusLayer();
        this.required = new WsiRequiredRegionLayer({ visible: false });
        this.focusLayer = new PatchFocusLayer();
        this.patches = new Map();
        this.patchListEl = document.getElementById('annotation-list');
        this.patchHeaderEl = document.querySelector('.annotation-group > .panel-header');
        this.displayPanel = null;
        this.lastRegionAction = null;
        this.selectedPatch = null;
        this.patchFocusActive = false;
        this.savedWsiView = null;
        this.lastWsiViewBeforePatchOpen = null;
        this.layerVisibilityBeforePatchView = null;
        this.toolbarToggle = null;
        this.patchContextMenu = null;
        this.editor = new CellAnnotationEditor({
            api,
            viewer,
            statusLayer: this.status,
            onStatus: this.setStatus,
            onSaved: (patch) => this.updatePatch(patch),
        });
        this._setupRightPanel();
        this._setupToolbarToggle();
        this.viewer.addOverlayLayer(this.required);
        this.viewer.addOverlayLayer(this.status);
        this.viewer.addOverlayLayer(this.grid);
        this.viewer.addOverlayLayer(this.focusLayer);
        this._bindEvents();
    }

    _setupRightPanel() {
        document.body.classList.add('cell-patch-workflow-page');
        if (this.patchHeaderEl) this.patchHeaderEl.textContent = 'Required Patches';
        document.getElementById('progress-label')?.closest('.panel-section')?.classList.add('cell-patch-hidden-progress');
        this._setupDisplayPanel();
        this.renderPatchList();
    }

    _setupDisplayPanel() {
        if (document.getElementById('cell-patch-display-panel')) return;
        const host = document.querySelector('.annotation-group');
        if (!host) return;
        const panel = document.createElement('div');
        panel.id = 'cell-patch-display-panel';
        panel.className = 'cell-patch-display-panel';
        panel.innerHTML = `
            <div class="cell-patch-display-title">Patch Overlay</div>
            <label class="cell-patch-display-row">
                <span>Patch border</span>
                <input id="cell-patch-border-width" type="range" min="0.5" max="6" step="0.5" value="1">
                <output id="cell-patch-border-width-value">1 px</output>
            </label>
            <label class="cell-patch-display-row">
                <span>Patch fill</span>
                <input id="cell-patch-fill-opacity" type="range" min="0" max="60" step="5" value="5">
                <output id="cell-patch-fill-opacity-value">5%</output>
            </label>
        `;
        host.appendChild(panel);
        this.displayPanel = panel;
        const formatPx = (value) => Number(value).toFixed(1).replace(/\.0$/, '');
        const apply = () => {
            const patchBorder = Number(panel.querySelector('#cell-patch-border-width')?.value || 1);
            const patchFill = Number(panel.querySelector('#cell-patch-fill-opacity')?.value || 5);
            this.grid.lineWidth = 1;
            this.status.setStyle({ strokeWidth: patchBorder, fillOpacity: patchFill / 100 });
            panel.querySelector('#cell-patch-border-width-value').textContent = `${formatPx(patchBorder)} px`;
            panel.querySelector('#cell-patch-fill-opacity-value').textContent = `${patchFill}%`;
            this.viewer?.requestRender?.();
        };
        panel.querySelectorAll('input').forEach(input => input.addEventListener('input', apply));
        apply();
    }

    _setupToolbarToggle() {
        const toolbar = document.getElementById('toolbar') || document.querySelector('.viewer-toolbar, #viewer-toolbar, nav.toolbar');
        if (!toolbar || document.getElementById('cell-patch-view-toggle')) return;
        const btn = document.createElement('button');
        btn.id = 'cell-patch-view-toggle';
        btn.type = 'button';
        btn.className = 'toolbar-btn patch-view-toolbar-toggle';
        btn.title = 'Toggle selected patch view (P)';
        btn.textContent = 'Patch View';
        btn.disabled = true;
        btn.addEventListener('click', () => this.togglePatchView());
        const spacer = toolbar.querySelector('.toolbar-spacer');
        toolbar.insertBefore(btn, spacer || null);
        this.toolbarToggle = btn;
        this._syncToolbarToggle();
    }

    _syncToolbarToggle() {
        if (!this.toolbarToggle) return;
        this.toolbarToggle.disabled = !this.selectedPatch;
        this.toolbarToggle.textContent = this.patchFocusActive ? 'WSI View' : 'Patch View';
        this.toolbarToggle.classList.toggle('active', this.patchFocusActive);
    }

    _bindEvents() {
        this.canvas?.addEventListener('click', (e) => {
            if (this.patchFocusActive) {
                e.preventDefault();
                e.stopImmediatePropagation?.();
                e.stopPropagation();
                return;
            }
            if (!this.slideId || this.viewer.drawMode) return;
            const rect = this.canvas.getBoundingClientRect();
            const [sx, sy] = this.viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
            const patch = this.grid.patchAt(sx, sy);
            if (!patch) return;
            const saved = this._findPatchRecord(patch);
            if (!saved) return;
            if ((saved.str_status || saved.status) === 'not_required') {
                if (saved.bool_manual_excluded) {
                    this.restorePatchToRequiredList({ ...patch, ...saved }).catch((err) => {
                        this.setStatus(`Patch restore failed: ${err.message}`);
                    });
                }
                return;
            }
            this.openPatch({ ...patch, ...saved });
            this.renderPatchList();
        }, true);

        this.canvas?.addEventListener('contextmenu', (e) => {
            if (this.patchFocusActive || !this.slideId || this.viewer.drawMode) return;
            const patch = this._patchFromPointerEvent(e);
            const saved = patch ? this._findPatchRecord(patch) : null;
            if (!saved) return;
            if ((saved.str_status || saved.status) === 'not_required' && !saved.bool_manual_excluded) return;
            e.preventDefault();
            e.stopPropagation();
            this._showPatchContextMenu({ ...patch, ...saved }, e.clientX, e.clientY);
        }, true);

        this.canvas?.addEventListener('dblclick', (e) => {
            if (this.patchFocusActive) {
                e.preventDefault();
                e.stopImmediatePropagation?.();
                e.stopPropagation();
                return;
            }
            if (!this.slideId || this.viewer.drawMode) return;
            const rect = this.canvas.getBoundingClientRect();
            const [sx, sy] = this.viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
            const patch = this.grid.patchAt(sx, sy);
            const saved = patch ? this._findPatchRecord(patch) : null;
            if (!patch || !saved || (saved.str_status || saved.status) === 'not_required') return;
            this.openPatch({ ...patch, ...saved }).then(() => this.enterPatchView());
            e.preventDefault();
            e.stopPropagation();
        }, true);

        window.addEventListener('keydown', (e) => {
            const tag = (e.target && e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;
            if (String(e.key || '').toLowerCase() !== 'p') return;
            if (!this.selectedPatch) return;
            this.togglePatchView();
            e.preventDefault();
        }, true);
    }

    async load(slideId) {
        this.slideId = slideId || '';
        this.patches.clear();
        this.exitPatchView({ restore: false });
        this.selectedPatch = null;
        this.lastWsiViewBeforePatchOpen = null;
        this._syncToolbarToggle();
        this.editor.close();
        this.renderPatchList();
        if (!this.slideId) return;
        const config = await this.api.getCellGridConfig(slideId);
        this.grid.setConfig(config);
        const regionPayload = await this.api.getCellRequiredRegions(slideId);
        this.required.setRegions(regionPayload.regions || []);
        await this.refreshPatches();
        this.viewer.requestRender();
    }

    async refreshPatches() {
        if (!this.slideId) return;
        const payload = await this.api.getCellPatches(this.slideId);
        this.patches.clear();
        for (const patch of payload.patches || []) {
            const id = patch.str_patch_id || patch.patch_id;
            if (id && this._patchMatchesCurrentGrid(patch)) {
                this.patches.set(id, { ...patch, patch_id: id });
            }
        }
        this.status.setPatches(Array.from(this.patches.values()));
        this.renderPatchList();
        this._syncAnnotationStatusPanel();
        this.viewer.requestRender();
    }

    updatePatch(patch) {
        const id = patch.str_patch_id || patch.patch_id;
        if (!id) return;
        if (!this._patchMatchesCurrentGrid(patch)) return;
        const normalized = { ...patch, patch_id: id };
        this.patches.set(id, normalized);
        if (this.selectedPatchId() === id) {
            this.selectedPatch = this._normalizePatchView({
                ...(this.selectedPatch || {}),
                ...normalized,
            });
            this.status.setSelectedPatch(id);
        }
        this.status.setPatches(Array.from(this.patches.values()));
        this.renderPatchList();
        this._syncAnnotationStatusPanel();
        this.viewer.requestRender();
    }

    _patchMatchesCurrentGrid(patch) {
        const config = this.grid?.config;
        if (!config) return true;
        const size = Number(config.patch_size_slide_px || 0);
        if (size <= 0) return true;
        const px = Number(patch.int_px ?? patch.px);
        const py = Number(patch.int_py ?? patch.py);
        if (!Number.isFinite(px) || !Number.isFinite(py)) return true;
        const expectedX = Math.round(px * size);
        const expectedY = Math.round(py * size);
        const actualX = Math.round(Number(patch.int_x ?? patch.x ?? expectedX));
        const actualY = Math.round(Number(patch.int_y ?? patch.y ?? expectedY));
        return Math.abs(actualX - expectedX) <= 1 && Math.abs(actualY - expectedY) <= 1;
    }

    _findPatchRecord(patch) {
        if (!patch) return null;
        const direct = this.patches.get(patch.patch_id || patch.str_patch_id);
        if (direct) return direct;
        const legacyId = `px_${Number(patch.px ?? patch.int_px ?? 0)}_py_${Number(patch.py ?? patch.int_py ?? 0)}`;
        return this.patches.get(legacyId) || null;
    }

    renderPatchList() {
        if (!this.patchListEl) return;
        const list = Array.from(this.patches.values())
            .filter(patch => (patch.str_status || patch.status || 'not_required') !== 'not_required')
            .sort((a, b) => {
                const ay = Number(a.int_py ?? a.py ?? 0);
                const by = Number(b.int_py ?? b.py ?? 0);
                const ax = Number(a.int_px ?? a.px ?? 0);
                const bx = Number(b.int_px ?? b.px ?? 0);
                return ay - by || ax - bx;
            });
        const statusCounts = list.reduce((acc, patch) => {
            const status = patch.str_status || patch.status || 'required';
            acc[status] = (acc[status] || 0) + 1;
            return acc;
        }, {});
        const countText = Object.entries(statusCounts)
            .map(([status, count]) => `${this._statusLabel(status)} ${count}`)
            .join(' / ');
        this.patchListEl.innerHTML = `
            <div class="patch-list-summary">
                <div>
                    <strong>${list.length}</strong>
                    <span>${list.length === 1 ? 'patch requires labeling' : 'patches require labeling'}</span>
                </div>
                <button type="button" class="patch-region-undo" ${this.canUndoRequiredRegion() ? '' : 'disabled'} title="Undo last required region">Undo Region</button>
            </div>
            ${countText ? `<div class="patch-list-counts">${this._escape(countText)}</div>` : ''}
        `;
        this.patchListEl.querySelector('.patch-region-undo')?.addEventListener('click', () => {
            this.undoLastRequiredRegion().catch((err) => {
                this.setStatus(`Required region undo failed: ${err.message}`);
            });
        });
        if (!this.slideId) {
            this.patchListEl.insertAdjacentHTML('beforeend', '<div class="patch-list-empty">Open a slide to load required patches.</div>');
            return;
        }
        if (!list.length) {
            this.patchListEl.insertAdjacentHTML('beforeend', '<div class="patch-list-empty">No required patches. Draw a required region to create patch tasks.</div>');
            return;
        }
        const body = document.createElement('div');
        body.className = 'patch-task-list';
        const header = document.createElement('div');
        header.className = 'patch-task-header';
        header.innerHTML = `
            <span>Patch</span>
            <span>Anno.</span>
            <span>Review</span>
            <span>Term.</span>
            <span>Memo</span>
        `;
        body.appendChild(header);
        for (const patch of list) {
            const id = patch.str_patch_id || patch.patch_id;
            const status = patch.str_status || patch.status || 'required';
            const workflow = this._patchWorkflowStatus(patch);
            const memo = this._patchMemo(patch);
            const memoHistory = this._patchMemoHistory(patch);
            const memoLabel = memo ? 'M' : (memoHistory.length ? 'H' : '-');
            const memoTitle = memo || (memoHistory.length ? `${memoHistory.length} previous memo(s)` : 'No memo');
            const row = document.createElement('div');
            row.tabIndex = 0;
            row.role = 'button';
            row.className = 'patch-task-row';
            row.dataset.patchId = id;
            row.dataset.status = status;
            row.dataset.hasMemo = memo ? 'current' : (memoHistory.length ? 'history' : '');
            if (id && id === this.selectedPatchId()) row.classList.add('selected');
            row.innerHTML = `
                <span class="patch-task-main">
                    <span class="patch-task-id">${this._escape(id)}</span>
                    <span class="patch-task-coord">X ${Number(patch.int_x ?? patch.x ?? 0).toLocaleString()} / Y ${Number(patch.int_y ?? patch.y ?? 0).toLocaleString()}</span>
                </span>
                <button type="button" class="patch-task-step" data-step="annotation" data-step-status="${this._escape(workflow.annotation)}">${this._escape(this._workflowLabel(workflow.annotation))}</button>
                <button type="button" class="patch-task-step" data-step="review" data-step-status="${this._escape(workflow.review)}">${this._escape(this._workflowLabel(workflow.review))}</button>
                <button type="button" class="patch-task-step" data-step="termination" data-step-status="${this._escape(workflow.termination)}">${this._escape(this._workflowLabel(workflow.termination))}</button>
                <button type="button" class="patch-task-memo-btn" title="${this._escape(memoTitle)}">${this._escape(memoLabel)}</button>
            `;
            row.addEventListener('click', () => this.openPatchFromList(id));
            row.addEventListener('keydown', (event) => {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                event.preventDefault();
                this.openPatchFromList(id);
            });
            row.querySelector('.patch-task-memo-btn')?.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                this.editPatchMemo(patch);
            });
            row.querySelectorAll('.patch-task-step').forEach(btn => {
                btn.addEventListener('click', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    this.updatePatchWorkflowStep(patch, btn.dataset.step).catch((err) => {
                        this.setStatus(`Patch workflow update failed: ${err.message}`);
                    });
                });
            });
            row.addEventListener('contextmenu', (event) => {
                event.preventDefault();
                event.stopPropagation();
                this._showPatchContextMenu(patch, event.clientX, event.clientY);
            });
            row.addEventListener('dblclick', (event) => {
                this.openPatchFromList(id).then(() => this.enterPatchView());
                event.preventDefault();
            });
            body.appendChild(row);
        }
        this.patchListEl.appendChild(body);
    }

    _patchWorkflowStatus(patch) {
        const status = patch.str_status || patch.status || 'required';
        return {
            annotation: patch.str_annotation_status || this._derivedWorkflowStatus(status, 'annotation'),
            review: patch.str_review_status || this._derivedWorkflowStatus(status, 'review'),
            termination: patch.str_termination_status || this._derivedWorkflowStatus(status, 'termination'),
        };
    }

    _derivedWorkflowStatus(status, step) {
        if (step === 'annotation') {
            if (status === 'required') return 'required';
            if (status === 'in_progress') return 'in_progress';
            if (status === 'not_required') return 'not_required';
            return 'completed';
        }
        if (step === 'review') {
            if (status === 'reviewed') return 'reviewed';
            if (status === 'rejected') return 'rejected';
            if (status === 'completed') return 'current';
            return 'pending';
        }
        if (step === 'termination') {
            if (status === 'reviewed' || status === 'rejected') return 'current';
            return 'pending';
        }
        return 'pending';
    }

    _workflowLabel(status) {
        return {
            required: 'Required',
            in_progress: 'Running',
            completed: 'Done',
            reviewed: 'Done',
            rejected: 'Rejected',
            current: 'Current',
            pending: '-',
            not_required: '-',
        }[status] || '-';
    }

    _patchCompletionPercent() {
        const list = Array.from(this.patches.values())
            .filter(patch => (patch.str_status || patch.status || 'not_required') !== 'not_required');
        if (!list.length) return 0;
        const done = list.filter(patch => {
            const workflow = this._patchWorkflowStatus(patch);
            return ['completed', 'reviewed', 'rejected'].includes(workflow.annotation);
        }).length;
        return Math.round((done / list.length) * 100);
    }

    _syncAnnotationStatusPanel() {
        const workflow = document.getElementById('annotation-status-workflow');
        const btn = workflow?.querySelector('[data-annotation-status="annotation"]');
        if (!workflow || !btn) return;
        let stateIcon = btn.nextElementSibling;
        if (!stateIcon || !stateIcon.classList.contains('annotation-step-state')) return;
        if (this.patchFocusActive && this.selectedPatch) {
            this._renderSelectedPatchWorkflowPanel(workflow);
            return;
        }
        workflow.classList.remove('is-patch-status');
        workflow.dataset.patchWorkflow = '';
        workflow.querySelectorAll('[data-annotation-status]').forEach((statusBtn) => {
            statusBtn.onclick = null;
            statusBtn.title = '';
            statusBtn.classList.remove('is-active', 'is-complete', 'is-running');
        });
        const pct = this._patchCompletionPercent();
        stateIcon.className = 'annotation-step-state annotation-step-percent';
        stateIcon.textContent = `${pct}%`;
        stateIcon.title = `Annotation completion: ${pct}%`;
    }

    _renderSelectedPatchWorkflowPanel(workflow) {
        if (!workflow || !this.selectedPatch) return;
        workflow.classList.add('is-patch-status');
        workflow.dataset.patchWorkflow = '1';
        const patch = this._findPatchRecord(this.selectedPatch) || this.selectedPatch;
        const states = this._patchWorkflowStatus(patch);
        const stepMap = {
            annotation: { label: 'Annotation', state: states.annotation },
            review: { label: 'Review', state: states.review },
            termination: { label: 'Termination', state: states.termination },
        };
        workflow.querySelectorAll('[data-annotation-status]').forEach((btn) => {
            const step = btn.dataset.annotationStatus;
            const info = stepMap[step] || stepMap.annotation;
            btn.innerHTML = `<span class="annotation-step-label">${info.label}</span>`;
            btn.classList.toggle('is-active', info.state === 'required' || info.state === 'in_progress' || info.state === 'current');
            btn.classList.toggle('is-complete', info.state === 'completed' || info.state === 'reviewed');
            btn.classList.toggle('is-running', info.state === 'in_progress');
            btn.disabled = false;
            btn.title = `Patch ${info.label}: ${this._workflowLabel(info.state)}`;
            btn.onclick = (event) => {
                event.preventDefault();
                event.stopImmediatePropagation();
                this.updatePatchWorkflowStep(patch, step).catch((err) => {
                    this.setStatus(`Patch workflow update failed: ${err.message}`);
                });
            };
            let stateIcon = btn.nextElementSibling;
            if (!stateIcon || !stateIcon.classList.contains('annotation-step-state')) return;
            const iconState = this._workflowIconState(info.state);
            stateIcon.className = `annotation-step-state annotation-step-icon is-${iconState}`;
            stateIcon.textContent = '';
            stateIcon.title = `Patch ${info.label}: ${this._workflowLabel(info.state)}`;
        });
    }

    _workflowIconState(state) {
        if (state === 'completed' || state === 'reviewed') return 'done';
        if (state === 'in_progress') return 'running';
        if (state === 'required' || state === 'current') return 'current';
        return 'pending';
    }

    async updatePatchWorkflowStep(patch, step) {
        const id = patch?.str_patch_id || patch?.patch_id;
        if (!this.slideId || !id || !step) return;
        const workflow = this._patchWorkflowStatus(patch);
        const next = { ...workflow };
        let status = patch.str_status || patch.status || 'required';
        if (step === 'annotation') {
            const order = ['required', 'in_progress', 'completed'];
            const current = workflow.annotation === 'completed' ? 'completed' : (workflow.annotation || 'required');
            const nextStatus = order[(Math.max(0, order.indexOf(current)) + 1) % order.length];
            next.annotation = nextStatus;
            status = nextStatus;
            if (nextStatus !== 'completed') {
                next.review = 'pending';
                next.termination = 'pending';
            }
        } else if (step === 'review') {
            const order = ['pending', 'reviewed', 'rejected'];
            const current = ['reviewed', 'rejected'].includes(workflow.review) ? workflow.review : 'pending';
            next.review = order[(order.indexOf(current) + 1) % order.length];
            if (next.review === 'pending') {
                status = 'completed';
                next.annotation = 'completed';
                next.termination = 'pending';
            } else {
                status = next.review;
                next.annotation = 'completed';
                next.termination = 'current';
            }
        } else if (step === 'termination') {
            const order = ['pending', 'current', 'completed'];
            const current = ['current', 'completed'].includes(workflow.termination) ? workflow.termination : 'pending';
            next.termination = order[(order.indexOf(current) + 1) % order.length];
            next.annotation = 'completed';
            if (workflow.review === 'pending') next.review = 'reviewed';
            status = next.review === 'rejected' ? 'rejected' : 'reviewed';
        }
        const result = await this.api.updatePatchStatus(this.slideId, id, status, {
            annotation_status: next.annotation,
            review_status: next.review,
            termination_status: next.termination,
            memo: this._patchMemo(patch),
            memo_history: this._patchMemoHistory(patch),
        });
        this.updatePatch({ ...patch, ...(result.patch || {}), patch_id: id });
        this.setStatus(`Patch ${step} updated: ${id}`);
    }

    _patchMemo(patch) {
        return String(patch?.str_memo || patch?.memo || '').trim();
    }

    _patchMemoHistory(patch) {
        return this._normalizeMemoHistory(patch?.list_memo_history || patch?.memo_history);
    }

    _normalizeMemoHistory(value) {
        const list = Array.isArray(value) ? value : [];
        return list
            .map(item => {
                if (typeof item === 'string') return { text: item.trim(), answer: '', accepted_at: '' };
                return {
                    text: String(item?.text ?? item?.memo ?? '').trim(),
                    answer: String(item?.answer ?? item?.reply ?? '').trim(),
                    accepted_at: String(item?.accepted_at ?? item?.created_at ?? '').trim(),
                };
            })
            .filter(item => item.text);
    }

    _patchFromPointerEvent(event) {
        if (!this.canvas || !this.viewer) return null;
        const rect = this.canvas.getBoundingClientRect();
        const [sx, sy] = this.viewer.canvasToScene(event.clientX - rect.left, event.clientY - rect.top);
        return this.grid.patchAt(sx, sy);
    }

    _closePatchContextMenu() {
        this.patchContextMenu?.remove();
        this.patchContextMenu = null;
    }

    _showPatchContextMenu(patch, clientX, clientY) {
        const id = patch?.str_patch_id || patch?.patch_id;
        if (!id) return;
        const isRemoved = (patch.str_status || patch.status) === 'not_required' && patch.bool_manual_excluded;
        this._closePatchContextMenu();
        const menu = document.createElement('div');
        menu.className = 'patch-context-menu';
        menu.innerHTML = `
            <div class="patch-context-title">${this._escape(id)}</div>
            <button type="button" data-action="memo">Memo</button>
            ${isRemoved
                ? '<button type="button" data-action="restore">Restore Patch</button>'
                : '<button type="button" data-action="remove" class="danger">Remove Patch</button>'}
        `;
        menu.addEventListener('click', (event) => {
            event.stopPropagation();
            const action = event.target?.closest('button')?.dataset?.action;
            if (action === 'memo') {
                this.editPatchMemo(patch);
            }
            if (action === 'remove') {
                this.removePatchFromRequiredList(patch).catch((err) => this.setStatus(`Patch remove failed: ${err.message}`));
            }
            if (action === 'restore') {
                this.restorePatchToRequiredList(patch).catch((err) => this.setStatus(`Patch restore failed: ${err.message}`));
            }
            if (action) this._closePatchContextMenu();
        });
        document.body.appendChild(menu);
        const width = menu.offsetWidth || 180;
        const height = menu.offsetHeight || 96;
        menu.style.left = `${Math.min(clientX, window.innerWidth - width - 8)}px`;
        menu.style.top = `${Math.min(clientY, window.innerHeight - height - 8)}px`;
        this.patchContextMenu = menu;
        setTimeout(() => {
            const close = () => {
                this._closePatchContextMenu();
                document.removeEventListener('click', close, true);
                document.removeEventListener('keydown', onKey, true);
            };
            const onKey = (event) => {
                if (event.key === 'Escape') close();
            };
            document.addEventListener('click', close, true);
            document.addEventListener('keydown', onKey, true);
        }, 0);
    }

    _openPatchMemoDialog({ patch, onSave, onAccept, onDelete, onDeleteHistory }) {
        const existing = document.querySelector('.memo-modal');
        if (existing) existing.remove();
        const id = patch?.str_patch_id || patch?.patch_id || 'patch';
        const value = this._patchMemo(patch);
        const hasCurrentMemo = Boolean(value);
        let historyList = this._patchMemoHistory(patch);
        const modal = document.createElement('div');
        modal.className = 'memo-modal';
        modal.innerHTML = `
            <div class="memo-dialog" role="dialog" aria-modal="true" aria-labelledby="patch-memo-title">
                <div class="memo-dialog-header">
                    <h2 id="patch-memo-title">Patch memo - ${this._escape(id)}</h2>
                    <button type="button" class="memo-close" aria-label="Close">x</button>
                </div>
                <div class="memo-dialog-body">
                    <label class="memo-current">
                        <span>${hasCurrentMemo ? 'Current memo' : 'Memo'}</span>
                        <textarea class="memo-textarea" rows="6" placeholder="Write memo..."${hasCurrentMemo ? ' readonly' : ''}>${this._escape(value)}</textarea>
                    </label>
                    <label class="memo-answer" ${hasCurrentMemo ? '' : 'hidden'}>
                        <span>Answer</span>
                        <textarea class="memo-answer-textarea" rows="4" placeholder="Write answer..."${hasCurrentMemo ? '' : ' disabled'}></textarea>
                    </label>
                    <div class="memo-history">
                        <div class="memo-history-title">Previous memo list</div>
                        <div class="memo-history-list"></div>
                    </div>
                </div>
                <div class="memo-dialog-footer">
                    <button type="button" class="small-btn memo-delete"${hasCurrentMemo ? ' hidden' : ''}>Delete</button>
                    <button type="button" class="small-btn memo-save"${hasCurrentMemo ? ' hidden' : ''}>Save</button>
                    <button type="button" class="small-btn primary memo-accept"${hasCurrentMemo ? '' : ' hidden'}>Accept</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        const textarea = modal.querySelector('.memo-textarea');
        const answerTextarea = modal.querySelector('.memo-answer-textarea');
        const listEl = modal.querySelector('.memo-history-list');
        const renderHistory = () => {
            listEl.innerHTML = '';
            if (!historyList.length) {
                const empty = document.createElement('div');
                empty.className = 'memo-history-empty';
                empty.textContent = 'No previous memos';
                listEl.appendChild(empty);
                return;
            }
            historyList.forEach((item, idx) => {
                const row = document.createElement('div');
                row.className = 'memo-history-item';
                row.innerHTML = `
                    <div class="memo-history-text">${this._escape(item.text)}</div>
                    ${item.answer ? `<div class="memo-history-answer"><strong>Answer</strong>${this._escape(item.answer)}</div>` : ''}
                    <time>${this._escape(item.accepted_at || '')}</time>
                    <button type="button" class="memo-history-delete" title="Delete previous memo">x</button>
                `;
                row.querySelector('.memo-history-delete')?.addEventListener('click', async () => {
                    if (!confirm('Delete previous memo?')) return;
                    const nextHistory = historyList.filter((_, itemIdx) => itemIdx !== idx);
                    await onDeleteHistory?.(nextHistory);
                    historyList = nextHistory;
                    renderHistory();
                });
                listEl.appendChild(row);
            });
        };
        const close = () => modal.remove();
        modal.querySelector('.memo-close')?.addEventListener('click', close);
        modal.addEventListener('mousedown', (event) => { if (event.target === modal) close(); });
        modal.querySelector('.memo-save')?.addEventListener('click', async () => {
            await onSave?.(textarea.value.trim());
            close();
        });
        modal.querySelector('.memo-accept')?.addEventListener('click', async () => {
            await onAccept?.(textarea.value.trim(), answerTextarea?.value.trim() || '');
            close();
        });
        modal.querySelector('.memo-delete')?.addEventListener('click', async () => {
            if (!textarea.value.trim() && !value) return close();
            if (!confirm('Delete current memo?')) return;
            await onDelete?.();
            close();
        });
        renderHistory();
        const focusTarget = hasCurrentMemo ? answerTextarea : textarea;
        focusTarget?.focus();
        focusTarget?.select();
    }

    async _savePatchMemoState(patch, memo, history) {
        const id = patch?.str_patch_id || patch?.patch_id;
        if (!this.slideId || !id) return;
        const status = patch.str_status || patch.status || 'required';
        const result = await this.api.updatePatchStatus(this.slideId, id, status, {
            memo,
            memo_history: this._normalizeMemoHistory(history),
        });
        this.updatePatch(result.patch || { ...patch, str_memo: memo, list_memo_history: history });
    }

    editPatchMemo(patch) {
        this._openPatchMemoDialog({
            patch,
            onSave: async (text) => {
                await this._savePatchMemoState(patch, text, this._patchMemoHistory(patch));
                this.setStatus(text ? 'Patch memo saved' : 'Patch memo cleared');
            },
            onAccept: async (text, answer) => {
                const history = this._patchMemoHistory(patch);
                if (text) history.unshift({ text, answer, accepted_at: new Date().toISOString() });
                await this._savePatchMemoState(patch, '', history);
                this.setStatus('Patch memo accepted');
            },
            onDelete: async () => {
                await this._savePatchMemoState(patch, '', this._patchMemoHistory(patch));
                this.setStatus('Patch memo deleted');
            },
            onDeleteHistory: async (nextHistory) => {
                await this._savePatchMemoState(patch, this._patchMemo(patch), nextHistory);
                this.setStatus('Previous patch memo deleted');
            },
        });
    }

    async removePatchFromRequiredList(patch) {
        const id = patch?.str_patch_id || patch?.patch_id;
        if (!this.slideId || !id) return;
        if (!confirm(`Remove patch from required list?\n${id}`)) return;
        await this.api.updatePatchStatus(this.slideId, id, 'not_required', {
            manual_excluded: true,
            memo: this._patchMemo(patch),
            memo_history: this._patchMemoHistory(patch),
        });
        if (this.selectedPatchId() === id) {
            this.selectedPatch = null;
            this.status.setSelectedPatch('');
            if (this.patchFocusActive) this.exitPatchView({ restore: true });
        }
        await this.refreshPatches();
        this.setStatus(`Patch removed from required list: ${id}`);
    }

    async restorePatchToRequiredList(patch) {
        const id = patch?.str_patch_id || patch?.patch_id;
        if (!this.slideId || !id) return;
        const result = await this.api.updatePatchStatus(this.slideId, id, 'required', {
            manual_excluded: false,
            memo: this._patchMemo(patch),
            memo_history: this._patchMemoHistory(patch),
        });
        const restored = {
            ...patch,
            ...(result.patch || {}),
            patch_id: id,
            str_status: 'required',
            bool_manual_excluded: false,
        };
        this.updatePatch(restored);
        await this.openPatch(restored);
        this.setStatus(`Patch restored: ${id}`);
    }

    async openPatchFromList(patchId) {
        if (!patchId || !this.slideId) return;
        const saved = this.patches.get(patchId);
        if (!saved) return;
        const patch = this.grid.patchAt(Number(saved.int_x ?? saved.x ?? 0) + 1, Number(saved.int_y ?? saved.y ?? 0) + 1);
        await this.openPatch({
            ...(patch || {}),
            ...saved,
            patch_id: patchId,
            x: Number(saved.int_x ?? saved.x ?? patch?.x ?? 0),
            y: Number(saved.int_y ?? saved.y ?? patch?.y ?? 0),
            w: Number(saved.int_w ?? saved.w ?? patch?.w ?? 0),
            h: Number(saved.int_h ?? saved.h ?? patch?.h ?? 0),
        });
        this.renderPatchList();
    }

    async openPatch(patch) {
        if (!patch || !this.slideId) return;
        if (!this.patchFocusActive && !this.lastWsiViewBeforePatchOpen) {
            this.lastWsiViewBeforePatchOpen = {
                viewCenterX: this.viewer.viewCenterX,
                viewCenterY: this.viewer.viewCenterY,
                zoom: this.viewer.zoom,
            };
        }
        this.selectedPatch = this._normalizePatchView(patch);
        await this.editor.open(this.slideId, this.selectedPatch);
        if (this.patchFocusActive) {
            this.viewer.setViewBounds?.(this.selectedPatch);
            this.focusLayer.setPatch(this.selectedPatch);
            this._fitPatchView(this.selectedPatch);
        }
        this.renderPatchList();
        this._scrollSelectedPatchIntoView();
        this._syncAnnotationStatusPanel();
        this._syncToolbarToggle();
    }

    _scrollSelectedPatchIntoView() {
        const id = this.selectedPatchId();
        if (!id || !this.patchListEl) return;
        const row = this.patchListEl.querySelector(`.patch-task-row[data-patch-id="${CSS.escape(id)}"]`);
        row?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }

    selectedPatchId() {
        return this.selectedPatch?.patch_id || this.selectedPatch?.str_patch_id || this.status.selectedPatchId || '';
    }

    _normalizePatchView(patch) {
        return {
            ...patch,
            patch_id: patch.patch_id || patch.str_patch_id,
            x: Number(patch.x ?? patch.int_x ?? 0),
            y: Number(patch.y ?? patch.int_y ?? 0),
            w: Number(patch.w ?? patch.int_w ?? 0),
            h: Number(patch.h ?? patch.int_h ?? 0),
        };
    }

    _fitPatchView(patch) {
        if (!patch || !this.viewer) return;
        const w = Number(patch.w || 0);
        const h = Number(patch.h || 0);
        if (w <= 0 || h <= 0) return;
        this.viewer.viewCenterX = Number(patch.x || 0) + w / 2;
        this.viewer.viewCenterY = Number(patch.y || 0) + h / 2;
        const fitZoom = Math.min(this.viewer._viewW / w, this.viewer._viewH / h) * 0.98;
        this.viewer.setZoom(Math.max(this.viewer.minZoom, Math.min(this.viewer.maxZoom, fitZoom)));
        this.viewer.requestRender();
        this.viewer.onViewChange?.();
    }

    enterPatchView() {
        if (!this.selectedPatch || this.patchFocusActive) return;
        this.savedWsiView = this.lastWsiViewBeforePatchOpen || {
            viewCenterX: this.viewer.viewCenterX,
            viewCenterY: this.viewer.viewCenterY,
            zoom: this.viewer.zoom,
        };
        this.patchFocusActive = true;
        this.layerVisibilityBeforePatchView = {
            required: this.required.visible,
            status: this.status.visible,
            grid: this.grid.visible,
        };
        this.required.visible = false;
        this.status.visible = false;
        this.grid.visible = false;
        this.viewer.setViewBounds?.(this.selectedPatch);
        this.focusLayer.setPatch(this.selectedPatch);
        this._fitPatchView(this.selectedPatch);
        this.renderPatchList();
        this._syncToolbarToggle();
        this._syncAnnotationStatusPanel();
        this.setStatus(`Patch view: ${this.selectedPatch.patch_id}`);
    }

    exitPatchView({ restore = true } = {}) {
        if (!this.patchFocusActive && !this.focusLayer.visible) return;
        this.patchFocusActive = false;
        this.focusLayer.clear();
        if (this.layerVisibilityBeforePatchView) {
            this.required.visible = this.layerVisibilityBeforePatchView.required;
            this.status.visible = this.layerVisibilityBeforePatchView.status;
            this.grid.visible = this.layerVisibilityBeforePatchView.grid;
        }
        this.viewer.setViewBounds?.(null);
        if (restore && this.savedWsiView) {
            this.viewer.viewCenterX = this.savedWsiView.viewCenterX;
            this.viewer.viewCenterY = this.savedWsiView.viewCenterY;
            this.viewer.zoom = this.savedWsiView.zoom;
            this.viewer._clampView?.();
            this.viewer._emitZoomChange?.();
        }
        this.savedWsiView = null;
        this.lastWsiViewBeforePatchOpen = null;
        this.layerVisibilityBeforePatchView = null;
        this.viewer.requestRender();
        this.renderPatchList();
        this._syncToolbarToggle();
        this._syncAnnotationStatusPanel();
        this.setStatus('WSI view restored');
    }

    togglePatchView() {
        if (this.patchFocusActive) {
            this.exitPatchView();
        } else {
            this.enterPatchView();
        }
    }

    _statusLabel(status) {
        return {
            required: 'Required',
            in_progress: 'In Progress',
            completed: 'Completed',
            reviewed: 'Reviewed',
            rejected: 'Rejected',
            not_required: 'Not Required',
        }[status] || 'Required';
    }

    _escape(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    canUndoRequiredRegion() {
        return Boolean(this.slideId && this.required.toApiRegions().length);
    }

    async undoLastRequiredRegion() {
        if (!this.canUndoRequiredRegion()) return false;
        const regions = this.required.toApiRegions();
        const targetId = this.lastRegionAction?.regionId;
        let nextRegions = regions;
        if (targetId) {
            const idx = regions.findIndex(region => region.id === targetId);
            if (idx >= 0) nextRegions = regions.filter((_, regionIdx) => regionIdx !== idx);
        }
        if (nextRegions === regions) nextRegions = regions.slice(0, -1);
        await this.api.saveCellRequiredRegions(this.slideId, nextRegions);
        await this.api.recomputeCellPatchStatus(this.slideId);
        const regionPayload = await this.api.getCellRequiredRegions(this.slideId);
        this.required.setRegions(regionPayload.regions || []);
        this.lastRegionAction = null;
        await this.refreshPatches();
        this.setStatus('Required region undone and patch status recomputed');
        this.viewer?.requestRender?.();
        return true;
    }

    async addRequiredRegionFromAnnotation(annotation) {
        if (!this.slideId || !annotation) return;
        const coords = annotation.coordinates || [];
        if (coords.length < 3) return;
        const regions = this.required.toApiRegions();
        const regionId = `region_${Date.now()}`;
        regions.push({
            id: regionId,
            type: 'annotation_required_region',
            points: coords.map(pt => [Number(pt[0]), Number(pt[1])]),
        });
        await this.api.saveCellRequiredRegions(this.slideId, regions);
        await this.api.recomputeCellPatchStatus(this.slideId);
        const regionPayload = await this.api.getCellRequiredRegions(this.slideId);
        this.required.setRegions(regionPayload.regions || []);
        this.lastRegionAction = { regionId };
        await this.refreshPatches();
        await this.onRequiredRegionSaved({ regionId });
        this.setStatus('Required region saved and patch status recomputed');
    }
}
