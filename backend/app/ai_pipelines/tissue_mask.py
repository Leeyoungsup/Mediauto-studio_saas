"""text text text — γ text + H-DAB text + Otsu + text text.

routers/ai.py text _run_detection / _run_marker_detection_pipeline text text.
text text text text text text GPU text text text.
"""

import numpy as np

# ── tissue_mask text text text ──
# text v_out = 255 * (v_in/255) ^ γ text text text H-DAB/Otsu/text text text.
# γ text text text text text text text definite_bg text text text text text
# text. ai_mask_test.ipynb text text γ=4.0 text text stroma/text text text
# text text text text text text text text text text text text.
FLOAT_TISSUE_MASK_GAMMA = 4.0
_NP_TISSUE_MASK_GAMMA_LUT = np.clip(
    np.power(np.arange(256, dtype=np.float32) / 255.0,
             FLOAT_TISSUE_MASK_GAMMA) * 255.0,
    0, 255,
).astype(np.uint8)


def create_tissue_mask(slide, icc_transform=None):
    """text text text — γ text text H-DAB text → (Hem ∪ DAB ∪ text) − text text.

    text Hematoxylin Otsu text DAB text text text text(H text text)text
    text text text text text text text text text. text:
      0) text γ=4.0 text text — text text text definite_bg text text text
      1) H-DAB color deconvolution (Ruifrok & Johnston 2001) → H / DAB text text
      2) text text Otsu → text text text
      3) text text(text) Otsu → text text text
      4) Union text, text text text(text text text text 95% text) text text

    icc_transform text text text text text AI text text text text.
    """
    import cv2

    try:
        downsample = 128
        thumbnail = slide.get_thumbnail((
            slide.dimensions[0] // downsample,
            slide.dimensions[1] // downsample,
        ))
        if icc_transform is not None:
            from PIL import ImageCms
            thumbnail = thumbnail.convert('RGB')
            ImageCms.applyTransform(thumbnail, icc_transform, inPlace=True)
        thumbnail = np.array(thumbnail)
        if len(thumbnail.shape) == 3:
            rgb = thumbnail[:, :, :3]
        else:
            rgb = cv2.cvtColor(thumbnail, cv2.COLOR_GRAY2RGB)

        # ── text text (γ=4.0) ──
        # rgb text uint8 text LUT text text text text. text text text γ text text.
        rgb = _NP_TISSUE_MASK_GAMMA_LUT[rgb]

        # ── H-DAB color deconvolution (Ruifrok & Johnston, 2001) ──
        stain_matrix = np.array([
            [0.650, 0.704, 0.286],   # Hematoxylin
            [0.268, 0.570, 0.776],   # DAB
            [0.711, 0.423, 0.500],   # Residual
        ], dtype=np.float64)
        stain_matrix = stain_matrix / np.linalg.norm(stain_matrix, axis=1, keepdims=True)
        deconv_matrix = np.linalg.inv(stain_matrix)

        rgb_f = np.maximum(rgb.astype(np.float64), 1.0)
        od = -np.log(rgb_f / 255.0)
        h, w = rgb.shape[:2]
        stain_od = (od.reshape(-1, 3) @ deconv_matrix.T).reshape(h, w, 3)

        hematoxylin_od = np.clip(stain_od[:, :, 0], 0, None)
        dab_od = np.clip(stain_od[:, :, 1], 0, None)

        hem_max = max(np.percentile(hematoxylin_od, 99.5), 0.01)
        dab_max = max(np.percentile(dab_od, 99.5), 0.01)
        hem_u8 = np.clip(hematoxylin_od / hem_max * 255, 0, 255).astype(np.uint8)
        dab_u8 = np.clip(dab_od / dab_max * 255, 0, 255).astype(np.uint8)

        _, hem_mask = cv2.threshold(hem_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, dab_mask = cv2.threshold(dab_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # ── text(text std) — text text text text text ──
        np_gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gray_f = np_gray.astype(np.float32)
        ksize = (15, 15)
        local_mean = cv2.blur(gray_f, ksize)
        local_sq_mean = cv2.blur(gray_f ** 2, ksize)
        local_std = np.sqrt(np.maximum(local_sq_mean - local_mean ** 2, 0))
        std_scaled = np.clip(local_std * 10, 0, 255).astype(np.uint8)
        _, texture_mask = cv2.threshold(
            std_scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # ── text text text text (text text text 95% text) ──
        hist = cv2.calcHist([np_gray], [0], None, [256], [0, 256]).flatten()
        bg_peak = int(np.argmax(hist[128:]) + 128)
        definite_bg = (np_gray >= int(bg_peak * 0.95))

        mask = (hem_mask > 0) | (dab_mask > 0) | (texture_mask > 0)
        mask[definite_bg] = False
        mask = (mask.astype(np.uint8)) * 255

        # text text text CLOSE text text text text text text
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

        # ── text text text text text ──
        # → text text(text text text text text)text text tissue text text
        # → text text text text text text
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        filled = np.zeros_like(mask)
        int_min_area = max(int(h * w * 0.0005), 50)  # text text 0.05% text
        for cnt in contours:
            if cv2.contourArea(cnt) < int_min_area:
                continue
            cv2.drawContours(filled, [cnt], -1, 255, thickness=cv2.FILLED)
        mask = filled

        target_w = slide.dimensions[0] // 64
        target_h = slide.dimensions[1] // 64
        mask = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        return mask
    except Exception:
        w, h = slide.dimensions
        return np.ones((h // 64, w // 64), dtype=np.uint8) * 255


def _rects_intersect(rect_a, rect_b) -> bool:
    ax0, ax1, ay0, ay1 = rect_a
    bx0, bx1, by0, by1 = rect_b
    return ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1


def _patch_in_roi(px: int, py: int, image_size: int, roi_polygons) -> bool:
    if not roi_polygons:
        return True
    cx, cy = px + image_size // 2, py + image_size // 2
    return any(
        min(p[0] for p in poly) <= cx <= max(p[0] for p in poly) and
        min(p[1] for p in poly) <= cy <= max(p[1] for p in poly)
        for poly in roi_polygons
    )


def build_valid_patch_list(slide, width: int, height: int, image_size: int,
                           roi_polygons=None, icc_transform=None):
    """Return AI patch origins, using Philips data envelopes when available."""
    rects = [
        tuple(int(v) for v in rect)
        for rect in getattr(slide, "data_envelope_rectangles", [])
        if len(rect) == 4
    ]
    valid_patch_list = []

    if rects:
        for pr in range(width // image_size - 1):
            for pc in range(height // image_size - 1):
                px, py = pr * image_size, pc * image_size
                patch_rect = (px, px + image_size - 1, py, py + image_size - 1)
                if not any(_rects_intersect(patch_rect, rect) for rect in rects):
                    continue
                if not _patch_in_roi(px, py, image_size, roi_polygons):
                    continue
                valid_patch_list.append((px, py))
        return valid_patch_list, "data_envelope"

    thumb_mask = create_tissue_mask(slide, icc_transform=icc_transform)
    for pr in range(width // image_size - 1):
        for pc in range(height // image_size - 1):
            mx = (pr * image_size) // 64
            my = (pc * image_size) // 64
            if np.sum(thumb_mask[my:my + image_size // 64,
                                 mx:mx + image_size // 64]) == 0:
                continue
            px, py = pr * image_size, pc * image_size
            if not _patch_in_roi(px, py, image_size, roi_polygons):
                continue
            valid_patch_list.append((px, py))
    return valid_patch_list, "tissue_mask"
