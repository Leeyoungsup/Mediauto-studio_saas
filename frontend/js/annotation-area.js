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
    const update = () => {
        for (const [button, shape] of [[rectangle, 'Rectangle'], [circle, 'Circle']]) {
            if (!button) continue;
            button.querySelector('text').textContent = `${selectedArea}mm²`;
            button.title = `${shape}: ${selectedArea} mm² — choose 1, 2, 4 or 8 mm²`;
            button.setAttribute('aria-label', button.title);
        }
    };
    update();
    for (const [button, mode] of [[rectangle, 'rect-1mm2'], [circle, 'circle-1mm2']]) {
        if (!button) continue;
        button.setAttribute('aria-haspopup', 'menu');
        button.setAttribute('aria-expanded', 'false');
        button.addEventListener('click', () => {
            if (owner === button && !menu.hidden) { close(); return; }
            close();
            owner = button;
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
                    if (activeViewer.drawMode !== mode) activate(mode);
                    activeViewer.requestRender();
                    close();
                    button.focus();
                });
                menu.append(option);
            }
            const rect = button.getBoundingClientRect();
            menu.style.left = `${Math.max(4, Math.min(rect.left, window.innerWidth - 180))}px`;
            menu.style.top = `${Math.min(rect.bottom + 6, window.innerHeight - 190)}px`;
            menu.hidden = false;
            button.setAttribute('aria-expanded', 'true');
            menu.querySelector('[aria-checked="true"]').focus();
        });
    }
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
