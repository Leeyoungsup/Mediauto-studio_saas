export const FIXED_AREAS = [1, 2, 4, 8];

function pixelsPerMm(info) {
    const x = Number(info?.mpp_x ?? info?.mpp);
    const y = Number(info?.mpp_y ?? info?.mpp);
    return x > 0 && y > 0 && Number.isFinite(x + y) ? [1000 / x, 1000 / y] : null;
}

export function fixedAreaCoordinates(shape, cx, cy, area, info) {
    const scale = pixelsPerMm(info);
    if (!scale || !FIXED_AREAS.includes(area)) return null;
    if (shape === 'rectangle') {
        const hx = Math.sqrt(area) * scale[0] / 2;
        const hy = Math.sqrt(area) * scale[1] / 2;
        return [[cx - hx, cy - hy], [cx + hx, cy - hy], [cx + hx, cy + hy], [cx - hx, cy + hy]];
    }
    const count = 128;
    // Preserve the requested area in the stored polygon approximation too.
    const radius = Math.sqrt(2 * area / (count * Math.sin(2 * Math.PI / count)));
    return Array.from({ length: count }, (_, i) => {
        const angle = i * 2 * Math.PI / count;
        return [cx + Math.cos(angle) * radius * scale[0], cy + Math.sin(angle) * radius * scale[1]];
    });
}

export function annotationAreaMm2(annotation, info) {
    if (!['polygon', 'rectangle'].includes(annotation?.type)) return null;
    const coords = annotation.coordinates;
    const scale = pixelsPerMm(info);
    if (!scale || !Array.isArray(coords) || coords.length < 3) return null;
    const [ox, oy] = coords[0];
    let twiceArea = 0;
    for (let i = 0; i < coords.length; i++) {
        const [x, y] = coords[i];
        const [nx, ny] = coords[(i + 1) % coords.length];
        twiceArea += (x - ox) * (ny - oy) - (nx - ox) * (y - oy);
    }
    const area = Math.abs(twiceArea) / (2 * scale[0] * scale[1]);
    return Number.isFinite(area) ? area : null;
}

export function annotationAreaLabel(annotation, info) {
    if (!['polygon', 'rectangle'].includes(annotation?.type)) return '';
    const area = annotationAreaMm2(annotation, info);
    if (area === null) return 'Area unavailable';
    return `${area.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: area < 0.01 ? 6 : 2 })} mm²`;
}

export function bindFixedAreaTools(viewer, rectangle, circle, activate) {
    const getViewer = typeof viewer === 'function' ? viewer : () => viewer;
    let selectedArea = 2;
    getViewer().fixedAreaMm2 = selectedArea;
    const menu = document.createElement('div');
    menu.className = 'fixed-area-menu';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Annotation area');
    menu.hidden = true;
    document.body.append(menu);
    let owner = null;
    const close = () => {
        menu.hidden = true;
        owner?.setAttribute('aria-expanded', 'false');
    };
    const controls = [];
    const update = () => {
        for (const { button, sizeButton, shape } of controls) {
            sizeButton.querySelector('.fixed-area-label').textContent = `${selectedArea} mm²`;
            button.title = `Draw ${shape.toLowerCase()}: ${selectedArea} mm²`;
            button.setAttribute('aria-label', button.title);
            sizeButton.title = `Change ${shape.toLowerCase()} area: ${selectedArea} mm²`;
            sizeButton.setAttribute('aria-label', sizeButton.title);
        }
    };
    for (const [button, mode, shape] of [[rectangle, 'rect-1mm2', 'Rectangle'], [circle, 'circle-1mm2', 'Circle']]) {
        if (!button) continue;
        const group = document.createElement('div');
        group.className = 'fixed-area-control';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', `${shape} fixed area tool`);
        button.before(group);
        group.append(button);
        const sizeButton = document.createElement('button');
        sizeButton.type = 'button';
        sizeButton.className = 'fixed-area-size';
        sizeButton.append(button.querySelector('.fixed-area-label'));
        const arrow = document.createElement('span');
        arrow.className = 'fixed-area-chevron';
        arrow.textContent = '▾';
        arrow.setAttribute('aria-hidden', 'true');
        sizeButton.append(arrow);
        group.append(sizeButton);
        sizeButton.setAttribute('aria-haspopup', 'menu');
        sizeButton.setAttribute('aria-expanded', 'false');
        controls.push({ button, sizeButton, shape });
        const syncDisabled = () => {
            sizeButton.disabled = button.disabled;
            if (button.disabled && owner === sizeButton) close();
        };
        syncDisabled();
        new MutationObserver(syncDisabled).observe(button, { attributes: true, attributeFilter: ['disabled'] });
        button.addEventListener('click', () => {
            if (button.disabled) return;
            close();
            const activeViewer = getViewer();
            activeViewer.fixedAreaMm2 = selectedArea;
            activate(mode);
            activeViewer.requestRender();
        });
        sizeButton.addEventListener('click', () => {
            if (button.disabled) return;
            if (owner === sizeButton && !menu.hidden) { close(); return; }
            close();
            owner = sizeButton;
            menu.replaceChildren();
            for (const area of FIXED_AREAS) {
                const option = document.createElement('button');
                option.type = 'button';
                option.textContent = `${area} mm²`;
                option.setAttribute('role', 'menuitemradio');
                option.setAttribute('aria-checked', String(area === selectedArea));
                option.addEventListener('click', () => {
                    if (button.disabled) { close(); return; }
                    selectedArea = area;
                    const activeViewer = getViewer();
                    activeViewer.fixedAreaMm2 = area;
                    update();
                    activeViewer.requestRender();
                    close();
                    sizeButton.focus();
                });
                menu.append(option);
            }
            const rect = sizeButton.getBoundingClientRect();
            menu.style.left = `${Math.max(4, Math.min(rect.left, window.innerWidth - 180))}px`;
            menu.style.top = `${Math.min(rect.bottom + 6, window.innerHeight - 190)}px`;
            menu.hidden = false;
            sizeButton.setAttribute('aria-expanded', 'true');
            menu.querySelector('[aria-checked="true"]').focus();
        });
    }
    update();
    document.addEventListener('pointerdown', event => {
        if (!menu.contains(event.target) && !owner?.contains(event.target)) close();
    });
    menu.addEventListener('keydown', event => {
        if (event.key === 'Escape') { close(); owner?.focus(); }
        if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
            event.preventDefault();
            const items = [...menu.children];
            const index = items.indexOf(document.activeElement);
            items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
        }
        if (event.key === 'Tab') close();
    });
    window.addEventListener('resize', close);
}
