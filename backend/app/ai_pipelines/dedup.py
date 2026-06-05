"""Shared post-processing for Quanti cell detection pipelines."""

from __future__ import annotations

from typing import Tuple

import numpy as np


DETECTION_PATCH_OVERLAP_UM = 10.0
GLOBAL_DEDUP_VERSION = "quanti-overlap-10um-global-dedup-v1"
GLOBAL_DEDUP_CENTER_RADIUS_UM = 8.0
GLOBAL_DEDUP_IOU_THRESHOLD = 0.3


def processing_metadata() -> dict:
    return {
        "patch_overlap_um": DETECTION_PATCH_OVERLAP_UM,
        "global_dedup_version": GLOBAL_DEDUP_VERSION,
        "global_dedup_center_radius_um": GLOBAL_DEDUP_CENTER_RADIUS_UM,
        "global_dedup_iou_threshold": GLOBAL_DEDUP_IOU_THRESHOLD,
    }


def cache_has_current_detection_postprocess(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    return (
        result.get("patch_overlap_um") == DETECTION_PATCH_OVERLAP_UM
        and result.get("global_dedup_version") == GLOBAL_DEDUP_VERSION
    )


def _box_iou(x0_a, y0_a, x1_a, y1_a, x0_b, y0_b, x1_b, y1_b) -> float:
    ix0 = max(float(x0_a), float(x0_b))
    iy0 = max(float(y0_a), float(y0_b))
    ix1 = min(float(x1_a), float(x1_b))
    iy1 = min(float(y1_a), float(y1_b))
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, float(x1_a) - float(x0_a)) * max(0.0, float(y1_a) - float(y0_a))
    area_b = max(0.0, float(x1_b) - float(x0_b)) * max(0.0, float(y1_b) - float(y0_b))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def apply_global_cell_dedup(
    all_x,
    all_y,
    all_conf,
    all_cls,
    all_x0,
    all_y0,
    all_x1,
    all_y1,
    float_mpp,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Class-aware WSI-level deduplication for overlapped detection tiles."""
    if len(all_x) == 0:
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    float_mpp_safe = float(float_mpp) if float_mpp and float_mpp > 0 else 0.25
    radius_px = GLOBAL_DEDUP_CENTER_RADIUS_UM / float_mpp_safe
    keep_mask = np.ones(len(all_x), dtype=bool)

    try:
        from scipy.spatial import cKDTree
    except Exception:
        cKDTree = None

    for class_id in np.unique(all_cls):
        class_indices = np.where(all_cls == class_id)[0]
        if len(class_indices) <= 1:
            continue

        order = class_indices[np.argsort(all_conf[class_indices])[::-1]]
        if cKDTree is not None:
            coords = np.column_stack((all_x[class_indices], all_y[class_indices]))
            tree = cKDTree(coords)
        else:
            tree = None

        for idx in order:
            if not keep_mask[idx]:
                continue

            if tree is not None:
                local_neighbors = tree.query_ball_point(
                    [float(all_x[idx]), float(all_y[idx])],
                    r=radius_px,
                )
                candidates = class_indices[local_neighbors]
            else:
                dx = all_x[class_indices] - all_x[idx]
                dy = all_y[class_indices] - all_y[idx]
                candidates = class_indices[(dx * dx + dy * dy) <= radius_px * radius_px]

            for other in candidates:
                if other == idx or not keep_mask[other]:
                    continue
                if all_conf[other] > all_conf[idx]:
                    continue
                iou = _box_iou(
                    all_x0[idx], all_y0[idx], all_x1[idx], all_y1[idx],
                    all_x0[other], all_y0[other], all_x1[other], all_y1[other],
                )
                if iou >= GLOBAL_DEDUP_IOU_THRESHOLD:
                    keep_mask[other] = False

    dropped = int(len(all_x) - int(np.count_nonzero(keep_mask)))
    if dropped <= 0:
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    return (
        all_x[keep_mask],
        all_y[keep_mask],
        all_conf[keep_mask],
        all_cls[keep_mask],
        all_x0[keep_mask],
        all_y0[keep_mask],
        all_x1[keep_mask],
        all_y1[keep_mask],
        dropped,
    )
