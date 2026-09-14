/** Enlarge a pane in place; keep all viewers and their editing state alive. */
export class MultiViewFocus {
    constructor({ container, grid, button, getPanes, getActivePane }) {
        Object.assign(this, { container, grid, button, getPanes, getActivePane });
        this.focusedPane = null;
        this.ready = false;
        button?.addEventListener('click', () => this.toggle());
        this.refresh();
    }

    bindPaneDoubleClick(pane, activate) {
        // Native dblclick timing follows the OS setting, which may accept slow clicks.
        let previousClick = null;
        let quickPair = false;
        pane.element.addEventListener('click', event => {
            const now = event.timeStamp;
            quickPair = Boolean(previousClick && event.button === 0
                && event.target === previousClick.target
                && now - previousClick.time >= 0 && now - previousClick.time <= 250
                && Math.hypot(event.clientX - previousClick.x, event.clientY - previousClick.y) <= 8);
            previousClick = event.button === 0
                ? { time: now, x: event.clientX, y: event.clientY, target: event.target }
                : null;
        }, true);
        pane.element.addEventListener('dblclick', event => {
            const withinClickWindow = quickPair;
            previousClick = null;
            quickPair = false;
            // Leave drawing gestures and the enlarged viewer's annotation navigation intact.
            if (!withinClickWindow || this.focusedPane || !this.ready || this.container.hidden || pane.element.hidden
                || !pane.slideInfo || !pane.error.hidden || pane.viewer.drawMode
                || event.target.closest('button, input, select, textarea, a')) return;
            event.preventDefault();
            event.stopPropagation();
            activate(pane);
            this.toggle(pane);
        }, true);
    }

    toggle(pane = this.getActivePane()) {
        if (this.focusedPane) {
            this.focusedPane = null;
        } else {
            if (!this.ready || this.container.hidden || !pane?.slideInfo || !pane.error.hidden || pane.element.hidden) return;
            this.focusedPane = pane;
        }
        this.refresh();
        requestAnimationFrame(() => {
            for (const item of this.getPanes()) {
                if (this.container.hidden || item.element.hidden || (this.focusedPane && item !== this.focusedPane)) continue;
                // Resizing changes the viewport, not the user's zoom or location.
                const { zoom, viewCenterX, viewCenterY } = item.viewer;
                item.viewer._resizeCanvas();
                Object.assign(item.viewer, { zoom, viewCenterX, viewCenterY });
                item.viewer.requestRender();
            }
        });
    }

    refresh() {
        this.grid?.classList.toggle('pane-focused', Boolean(this.focusedPane));
        for (const pane of this.getPanes()) {
            pane.element.classList.toggle('focused-pane', pane === this.focusedPane);
            if (pane.focusButton) {
                pane.focusButton.textContent = pane === this.focusedPane ? 'Back to Multi View' : 'Enlarge';
                pane.focusButton.setAttribute('aria-pressed', String(pane === this.focusedPane));
                pane.focusButton.disabled = !this.ready || !pane.slideInfo || !pane.error.hidden;
            }
        }
        if (this.button) {
            const pane = this.getActivePane();
            this.button.textContent = this.focusedPane ? 'Back to Multi View' : 'Enlarge Active';
            this.button.setAttribute('aria-pressed', String(Boolean(this.focusedPane)));
            this.button.disabled = !this.ready || (!this.focusedPane && (!pane?.slideInfo || !pane.error.hidden));
        }
    }

    reset() {
        this.ready = false;
        this.focusedPane = null;
        this.refresh();
    }
}
