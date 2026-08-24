"""AI-estimated stromal TIL scoring for Quanti H&E Breast results.

The clinical sTIL definition is area based. This module uses the available
Quanti H&E outputs to approximate that definition:

* denominator: segmented stroma within a configurable distance of segmented
  tumor (tumor-associated stroma approximation)
* numerator: lymphocyte and plasma-cell detections inside that stroma,
  converted to area with a calibration coefficient

The current segmentation model does not separately identify invasive tumor,
in-situ tumor, necrosis, or healthy glands. The returned metadata therefore
marks the score as calibration-required and not a clinical ground truth.
"""

from __future__ import annotations

import math
import os
from typing import Optional

import numpy as np


STIL_LYMPHOCYTE_CLASS_ID = 2
STIL_PLASMA_CLASS_ID = 3
STIL_SEG_STROMA_CLASS_ID = 1
STIL_SEG_TUMOR_CLASS_ID = 3


def _positive_env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
        return value if math.isfinite(value) and value > 0 else default
    except (TypeError, ValueError):
        return default


# These defaults are implementation assumptions, not clinical cut-offs. Sites can
# replace them after pathologist calibration without changing application code.
STIL_DEFAULT_IMMUNE_CELL_AREA_UM2 = _positive_env_float(
    "QUANTI_HE_STIL_IMMUNE_CELL_AREA_UM2", round(math.pi * 3.0 * 3.0, 4),
)
STIL_DEFAULT_GRID_SIZE_UM = _positive_env_float("QUANTI_HE_STIL_GRID_SIZE_UM", 500.0)
STIL_DEFAULT_TUMOR_PROXIMITY_UM = _positive_env_float(
    "QUANTI_HE_STIL_TUMOR_PROXIMITY_UM", 500.0,
)
STIL_DEFAULT_MIN_CONFIDENCE = min(
    1.0, _positive_env_float("QUANTI_HE_STIL_MIN_CONFIDENCE", 0.1),
)

# Include calibration-sensitive defaults in the cache version. Changing an
# environment value therefore invalidates old full-slide results automatically.
STIL_SCORE_VERSION = (
    "quanti-he-stil-area-v2"
    f"-a{STIL_DEFAULT_IMMUNE_CELL_AREA_UM2:g}"
    f"-g{STIL_DEFAULT_GRID_SIZE_UM:g}"
    f"-p{STIL_DEFAULT_TUMOR_PROXIMITY_UM:g}"
    f"-c{STIL_DEFAULT_MIN_CONFIDENCE:g}"
)


def _roi_mask(shape, roi_polygons, region_offset, scene_px_per_mask_px):
    if not roi_polygons:
        return np.ones(shape, dtype=bool)

    import cv2

    mask = np.zeros(shape, dtype=np.uint8)
    ox, oy = region_offset
    polygons = []
    for polygon in roi_polygons:
        if not polygon or len(polygon) < 3:
            continue
        points = np.asarray([
            [
                int(round((float(point[0]) - ox) / scene_px_per_mask_px)),
                int(round((float(point[1]) - oy) / scene_px_per_mask_px)),
            ]
            for point in polygon
        ], dtype=np.int32)
        polygons.append(points)
    if polygons:
        cv2.fillPoly(mask, polygons, 1)
    return mask.astype(bool)


def unavailable_stil_score(reason: str) -> dict:
    return {
        "version": STIL_SCORE_VERSION,
        "available": False,
        "reason": reason,
        "clinical_use": False,
        "calibration_status": "required",
    }


def compute_stil_score(
    prediction_mask,
    metadata: dict,
    all_x,
    all_y,
    all_cls,
    all_conf,
    roi_polygons: Optional[list] = None,
    *,
    immune_cell_area_um2: float = STIL_DEFAULT_IMMUNE_CELL_AREA_UM2,
    grid_size_um: float = STIL_DEFAULT_GRID_SIZE_UM,
    tumor_proximity_um: float = STIL_DEFAULT_TUMOR_PROXIMITY_UM,
    min_confidence: float = STIL_DEFAULT_MIN_CONFIDENCE,
) -> dict:
    """Compute a global AI-estimated sTIL score and a local score grid."""

    import cv2

    immune_cell_area_um2 = max(0.0, float(immune_cell_area_um2))
    grid_size_um = max(1.0, float(grid_size_um))
    tumor_proximity_um = max(1.0, float(tumor_proximity_um))
    min_confidence = min(1.0, max(0.0, float(min_confidence)))

    mask = np.asarray(prediction_mask)
    if mask.ndim != 2 or mask.size == 0:
        return unavailable_stil_score("Segmentation mask is unavailable")

    output_mpp = float(metadata.get("output_mpp") or 4.0)
    wsi_mpp = float(metadata.get("wsi_mpp") or 0.25)
    if output_mpp <= 0 or wsi_mpp <= 0:
        return unavailable_stil_score("Slide resolution metadata is unavailable")

    region_offset_raw = metadata.get("region_offset") or (0, 0)
    region_offset = (float(region_offset_raw[0]), float(region_offset_raw[1]))
    scene_px_per_mask_px = output_mpp / wsi_mpp
    analysis_roi = _roi_mask(mask.shape, roi_polygons, region_offset, scene_px_per_mask_px)

    tumor_mask = (mask == STIL_SEG_TUMOR_CLASS_ID) & analysis_roi
    stroma_mask = (mask == STIL_SEG_STROMA_CLASS_ID) & analysis_roi
    if not np.any(tumor_mask):
        return unavailable_stil_score("No segmented tumor area was found")
    if not np.any(stroma_mask):
        return unavailable_stil_score("No segmented stromal area was found")

    # Distance is measured from every non-tumor pixel to the nearest tumor
    # pixel. Restricting stroma by this distance excludes remote slide stroma
    # while retaining intratumoral/peritumoral stroma around the tumor bulk.
    distance_to_tumor = cv2.distanceTransform(
        (~tumor_mask).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE,
    )
    proximity_px = max(1.0, float(tumor_proximity_um) / output_mpp)
    tas_mask = stroma_mask & (distance_to_tumor <= proximity_px)
    tas_pixel_count = int(np.count_nonzero(tas_mask))
    if tas_pixel_count == 0:
        return unavailable_stil_score("No tumor-associated stromal area was found")

    mask_pixel_area_um2 = output_mpp * output_mpp
    tas_area_um2 = tas_pixel_count * mask_pixel_area_um2
    tas_area_mm2 = tas_area_um2 / 1_000_000.0
    tumor_area_mm2 = float(np.count_nonzero(tumor_mask) * mask_pixel_area_um2 / 1_000_000.0)

    x_values = np.asarray(all_x, dtype=np.float64)
    y_values = np.asarray(all_y, dtype=np.float64)
    class_values = np.asarray(all_cls, dtype=np.int32)
    confidence_values = np.asarray(all_conf, dtype=np.float64)
    cell_count = min(len(x_values), len(y_values), len(class_values), len(confidence_values))
    x_values = x_values[:cell_count]
    y_values = y_values[:cell_count]
    class_values = class_values[:cell_count]
    confidence_values = confidence_values[:cell_count]

    mx = np.floor((x_values - region_offset[0]) / scene_px_per_mask_px).astype(np.int64)
    my = np.floor((y_values - region_offset[1]) / scene_px_per_mask_px).astype(np.int64)
    valid = (
        (mx >= 0) & (mx < mask.shape[1]) &
        (my >= 0) & (my < mask.shape[0]) &
        (confidence_values >= float(min_confidence))
    )
    immune = (class_values == STIL_LYMPHOCYTE_CLASS_ID) | (class_values == STIL_PLASMA_CLASS_ID)
    in_tas = np.zeros(cell_count, dtype=bool)
    valid_indices = np.where(valid & immune)[0]
    if len(valid_indices):
        in_tas[valid_indices] = tas_mask[my[valid_indices], mx[valid_indices]]

    lymphocyte_mask = in_tas & (class_values == STIL_LYMPHOCYTE_CLASS_ID)
    plasma_mask = in_tas & (class_values == STIL_PLASMA_CLASS_ID)
    lymphocyte_count = int(np.count_nonzero(lymphocyte_mask))
    plasma_count = int(np.count_nonzero(plasma_mask))
    immune_count = lymphocyte_count + plasma_count
    immune_area_um2 = immune_count * float(immune_cell_area_um2)
    score_percent = min(100.0, immune_area_um2 / tas_area_um2 * 100.0)

    grid_px = max(1, int(round(float(grid_size_um) / output_mpp)))
    grid_rows = int(math.ceil(mask.shape[0] / grid_px))
    grid_cols = int(math.ceil(mask.shape[1] / grid_px))
    lymph_grid = np.zeros((grid_rows, grid_cols), dtype=np.int32)
    plasma_grid = np.zeros((grid_rows, grid_cols), dtype=np.int32)
    if lymphocyte_count:
        np.add.at(lymph_grid, (my[lymphocyte_mask] // grid_px, mx[lymphocyte_mask] // grid_px), 1)
    if plasma_count:
        np.add.at(plasma_grid, (my[plasma_mask] // grid_px, mx[plasma_mask] // grid_px), 1)

    ys, xs = np.where(tas_mask)
    row_min, row_max = int(ys.min() // grid_px), int(ys.max() // grid_px)
    col_min, col_max = int(xs.min() // grid_px), int(xs.max() // grid_px)
    heatmap_cells = []
    local_scores = []
    for row in range(row_min, row_max + 1):
        py0 = row * grid_px
        py1 = min(mask.shape[0], py0 + grid_px)
        for col in range(col_min, col_max + 1):
            px0 = col * grid_px
            px1 = min(mask.shape[1], px0 + grid_px)
            local_stroma_pixels = int(np.count_nonzero(tas_mask[py0:py1, px0:px1]))
            if local_stroma_pixels == 0:
                continue
            local_stroma_um2 = local_stroma_pixels * mask_pixel_area_um2
            local_lymph = int(lymph_grid[row, col])
            local_plasma = int(plasma_grid[row, col])
            local_score = min(
                100.0,
                (local_lymph + local_plasma) * float(immune_cell_area_um2) /
                local_stroma_um2 * 100.0,
            )
            local_scores.append(local_score)
            heatmap_cells.append([
                round(region_offset[0] + px0 * scene_px_per_mask_px, 2),
                round(region_offset[1] + py0 * scene_px_per_mask_px, 2),
                round((px1 - px0) * scene_px_per_mask_px, 2),
                round((py1 - py0) * scene_px_per_mask_px, 2),
                round(local_score, 2),
                round(local_stroma_um2 / 1_000_000.0, 6),
                local_lymph,
                local_plasma,
            ])

    return {
        "version": STIL_SCORE_VERSION,
        "available": True,
        "score_percent": round(score_percent, 2),
        "score_name": "AI-estimated stromal TIL",
        "method": "immune-cell calibrated area / tumor-associated stroma area",
        "clinical_use": False,
        "calibration_status": "required",
        "immune_cell_area_um2": round(float(immune_cell_area_um2), 4),
        "immune_area_um2": round(immune_area_um2, 2),
        "tumor_associated_stroma_area_mm2": round(tas_area_mm2, 4),
        "segmented_tumor_area_mm2": round(tumor_area_mm2, 4),
        "lymphocyte_count": lymphocyte_count,
        "plasma_count": plasma_count,
        "lymphocyte_density_cells_mm2": round(lymphocyte_count / tas_area_mm2, 2),
        "plasma_density_cells_mm2": round(plasma_count / tas_area_mm2, 2),
        "immune_density_cells_mm2": round(immune_count / tas_area_mm2, 2),
        "minimum_detection_confidence": round(float(min_confidence), 3),
        "tumor_proximity_um": round(float(tumor_proximity_um), 1),
        "limitations": [
            "The current segmentation model does not separately exclude in-situ tumor, necrosis, or healthy glands.",
            "Immune-cell occupied area uses a calibration coefficient and requires pathologist validation.",
        ],
        "spatial_heatmap": {
            "grid_size_um": round(float(grid_size_um), 1),
            "thresholds_percent": [0, 10, 30, 50, 100],
            "cells": heatmap_cells,
            "local_max_percent": round(max(local_scores), 2) if local_scores else 0.0,
            "local_mean_percent": round(float(np.mean(local_scores)), 2) if local_scores else 0.0,
            "global_score_is_area_weighted": True,
        },
    }
