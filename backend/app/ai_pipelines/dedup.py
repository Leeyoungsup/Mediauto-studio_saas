"""Shared post-processing for Quanti cell detection pipelines."""

from __future__ import annotations

from typing import Tuple

import numpy as np


DETECTION_PATCH_OVERLAP_UM = 10.0
DETECTION_EDGE_IGNORE_UM = 3.0
GLOBAL_DEDUP_VERSION = "quanti-overlap-10um-edge3um-global-nms-v8"
GLOBAL_NMS_IOU_THRESHOLD = 0.3
EXCLUDED_CLASS_SUPPRESSION_IOU_THRESHOLD = 0.3


def processing_metadata() -> dict:
    return {
        "patch_overlap_um": DETECTION_PATCH_OVERLAP_UM,
        "patch_edge_ignore_um": DETECTION_EDGE_IGNORE_UM,
        "global_dedup_version": GLOBAL_DEDUP_VERSION,
        "global_nms_iou_threshold": GLOBAL_NMS_IOU_THRESHOLD,
        "global_dedup_match_rule": "cross_class_iou_nms_visible_priority",
        "excluded_class_suppression_iou_threshold": EXCLUDED_CLASS_SUPPRESSION_IOU_THRESHOLD,
        "excluded_class_suppression_rule": "drop_excluded_class_boxes_overlapping_visible_boxes",
    }


def cache_has_current_detection_postprocess(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    return (
        result.get("patch_overlap_um") == DETECTION_PATCH_OVERLAP_UM
        and result.get("global_dedup_version") == GLOBAL_DEDUP_VERSION
    )


def patch_edge_keep_mask(
    local_x,
    local_y,
    patch_x: int,
    patch_y: int,
    slide_width: int,
    slide_height: int,
    image_size: int,
    float_mpp,
    edge_ignore_um: float = DETECTION_EDGE_IGNORE_UM,
) -> np.ndarray:
    """Keep detections away from internal patch edges; slide outer edges are preserved."""
    if len(local_x) == 0:
        return np.zeros(0, dtype=bool)
    float_mpp_safe = float(float_mpp) if float_mpp and float_mpp > 0 else 0.25
    margin_px = max(0.0, float(edge_ignore_um or 0.0) / float_mpp_safe)
    if margin_px <= 0:
        return np.ones(len(local_x), dtype=bool)

    keep = np.ones(len(local_x), dtype=bool)
    if int(patch_x) > 0:
        keep &= local_x >= margin_px
    if int(patch_y) > 0:
        keep &= local_y >= margin_px
    if int(patch_x) + int(image_size) < int(slide_width):
        keep &= local_x <= (float(image_size) - margin_px)
    if int(patch_y) + int(image_size) < int(slide_height):
        keep &= local_y <= (float(image_size) - margin_px)
    return keep


def _box_iou_np(box, boxes) -> np.ndarray:
    ix0 = np.maximum(float(box[0]), boxes[:, 0])
    iy0 = np.maximum(float(box[1]), boxes[:, 1])
    ix1 = np.minimum(float(box[2]), boxes[:, 2])
    iy1 = np.minimum(float(box[3]), boxes[:, 3])
    inter_w = np.maximum(0.0, ix1 - ix0)
    inter_h = np.maximum(0.0, iy1 - iy0)
    inter = inter_w * inter_h
    area_box = max(0.0, float(box[2]) - float(box[0])) * max(0.0, float(box[3]) - float(box[1]))
    area_boxes = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(0.0, boxes[:, 3] - boxes[:, 1])
    union = area_box + area_boxes - inter
    return np.divide(inter, union, out=np.zeros_like(inter, dtype=np.float32), where=union > 0)


def _nms_indices_np(boxes, scores, iou_threshold: float) -> np.ndarray:
    order = np.argsort(scores)[::-1]
    keep = []
    while len(order) > 0:
        idx = int(order[0])
        keep.append(idx)
        if len(order) == 1:
            break
        rest = order[1:]
        ious = _box_iou_np(boxes[idx], boxes[rest])
        order = rest[ious <= iou_threshold]
    return np.asarray(keep, dtype=np.int64)


def _nms_indices(boxes, scores, iou_threshold: float) -> np.ndarray:
    try:
        import torch
        import torchvision
        tensor_boxes = torch.as_tensor(boxes, dtype=torch.float32)
        tensor_scores = torch.as_tensor(scores, dtype=torch.float32)
        return torchvision.ops.nms(tensor_boxes, tensor_scores, iou_threshold).cpu().numpy()
    except Exception:
        return _nms_indices_np(boxes, scores, iou_threshold)


def suppress_excluded_classes_overlapping_visible(
    all_x,
    all_y,
    all_conf,
    all_cls,
    all_x0,
    all_y0,
    all_x1,
    all_y1,
    list_exclude,
    iou_threshold: float = EXCLUDED_CLASS_SUPPRESSION_IOU_THRESHOLD,
):
    """Drop hidden/excluded class boxes, such as Other, that duplicate visible boxes."""
    if len(all_x) == 0 or not list_exclude:
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    exclude_mask = np.isin(all_cls, list_exclude)
    visible_mask = ~exclude_mask
    if not exclude_mask.any() or not visible_mask.any():
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    excluded_idx = np.where(exclude_mask)[0]
    visible_idx = np.where(visible_mask)[0]
    visible_boxes = np.column_stack((
        all_x0[visible_idx],
        all_y0[visible_idx],
        all_x1[visible_idx],
        all_y1[visible_idx],
    )).astype(np.float32, copy=False)
    visible_centers = np.column_stack((all_x[visible_idx], all_y[visible_idx])).astype(np.float32, copy=False)

    try:
        from scipy.spatial import cKDTree
        tree = cKDTree(visible_centers)
        visible_w = np.maximum(0.0, visible_boxes[:, 2] - visible_boxes[:, 0])
        visible_h = np.maximum(0.0, visible_boxes[:, 3] - visible_boxes[:, 1])
        visible_diag = np.sqrt(visible_w * visible_w + visible_h * visible_h)
        query_radius = max(8.0, float(np.percentile(visible_diag, 95)) if len(visible_diag) else 64.0)
    except Exception:
        tree = None
        query_radius = 64.0

    keep_mask = np.ones(len(all_x), dtype=bool)
    for idx in excluded_idx:
        box = np.asarray([all_x0[idx], all_y0[idx], all_x1[idx], all_y1[idx]], dtype=np.float32)
        if tree is not None:
            local = tree.query_ball_point([float(all_x[idx]), float(all_y[idx])], r=query_radius)
            if not local:
                continue
            candidate_boxes = visible_boxes[np.asarray(local, dtype=np.int64)]
        else:
            dx = visible_centers[:, 0] - float(all_x[idx])
            dy = visible_centers[:, 1] - float(all_y[idx])
            local = np.where((dx * dx + dy * dy) <= query_radius * query_radius)[0]
            if len(local) == 0:
                continue
            candidate_boxes = visible_boxes[local]
        if np.any(_box_iou_np(box, candidate_boxes) >= iou_threshold):
            keep_mask[idx] = False

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
    list_exclude=None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """WSI-level IoU NMS for overlapped detection tiles."""
    if len(all_x) == 0:
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    boxes = np.column_stack((all_x0, all_y0, all_x1, all_y1)).astype(np.float32, copy=False)
    scores = all_conf.astype(np.float32, copy=True)
    if list_exclude:
        visible_mask = ~np.isin(all_cls, list_exclude)
        scores[visible_mask] += 1.0
    keep_indices = _nms_indices(boxes, scores, GLOBAL_NMS_IOU_THRESHOLD)
    keep_mask = np.zeros(len(all_x), dtype=bool)
    keep_mask[keep_indices] = True

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
