"""Quanti HE detection worker + epithelial reclassification overlay.

routers/ai.py text text text. desktop DetectionWorker.run() text text
text (text text → I/O text → text GPU text → Epithelial text).

Epithelial text Breast/Stomach text text text, text class 1 (Epithelial)
text connected-component text tumor text 6 (Tumor) / 7 (Benign) text text.
"""

import json
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from app.ai_pipelines.cache_paths import get_ai_cache_path
from app.ai_pipelines.task_state import (
    TaskCancelled,
    check_cancel,
    cleanup_cache_paths,
    is_cancel_requested,
    update_task,
)
from app.ai_pipelines.tissue_mask import create_tissue_mask
from app.config import settings
from app.priority import wait_if_viewer_busy
from app.slide_manager import slide_manager
from app.thread_slide_pool import get_thread_slide


def _compact_cell(cell):
    if isinstance(cell, (list, tuple)):
        return list(cell)
    if not isinstance(cell, dict):
        return cell
    compact = [
        round(float(cell.get("x", 0.0)), 2),
        round(float(cell.get("y", 0.0)), 2),
        int(cell.get("class_id", 0)),
        round(float(cell.get("confidence", 0.0)), 4),
    ]
    if all(k in cell for k in ("x0", "y0", "x1", "y1")):
        compact.extend([
            round(float(cell.get("x0", 0.0)), 2),
            round(float(cell.get("y0", 0.0)), 2),
            round(float(cell.get("x1", 0.0)), 2),
            round(float(cell.get("y1", 0.0)), 2),
        ])
    return compact


def _cell_has_bbox(cell) -> bool:
    if isinstance(cell, (list, tuple)):
        return len(cell) >= 8 and all(isinstance(cell[i], (int, float)) for i in range(4, 8))
    if isinstance(cell, dict):
        return all(k in cell for k in ("x0", "y0", "x1", "y1"))
    return False


def _compact_cached_result(result):
    if not isinstance(result, dict):
        return result, False
    cells = result.get("cells")
    bool_object_cell_cache = bool(cells and isinstance(cells, list) and isinstance(cells[0], dict))
    if isinstance(cells, list):
        result["cells"] = [_compact_cell(c) for c in cells if isinstance(c, (dict, list, tuple))]
        result["total_cells"] = len(result["cells"])
    return result, bool_object_cell_cache


# ── Stromal cell text text text text ──
# Stromal cell (class 5) text text confidence text text text text
# Stromal text text text text text. NMS text text text text text
# text text text text text text text text text Stromal + text
# text text text text text, text text.
STROMAL_CLASS_ID = 5
STROMAL_SUPPRESSION_RADIUS_UM = 10.0  # text text text text text (μm)
STROMAL_SUPPRESSION_CONF = 0.1        # text text text text confidence text


def _suppress_stromal_when_others_present(all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, float_mpp):
    """Stromal cell (class 5) text conf >= STROMAL_SUPPRESSION_CONF text text text
    text text text Stromal cell text text. KDTree text O((n_stromal + n_other) log n) text.

    Returns: (new_x, new_y, new_conf, new_cls, int_dropped) — text text text ndarray
        text + text Stromal cell text.
    """
    import numpy as np

    if len(all_cls) == 0:
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    np_stromal_mask = (all_cls == STROMAL_CLASS_ID)
    np_other_mask = (~np_stromal_mask) & (all_conf >= STROMAL_SUPPRESSION_CONF)
    if not np_stromal_mask.any() or not np_other_mask.any():
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    # mpp text 0/None text text fallback (40x text 0.25 μm/px)
    float_mpp_safe = float(float_mpp) if float_mpp and float_mpp > 0 else 0.25
    float_radius_px = STROMAL_SUPPRESSION_RADIUS_UM / float_mpp_safe

    np_stromal_idx = np.where(np_stromal_mask)[0]
    np_other_idx = np.where(np_other_mask)[0]

    np_stromal_xy = np.column_stack((all_x[np_stromal_idx], all_y[np_stromal_idx]))
    np_other_xy = np.column_stack((all_x[np_other_idx], all_y[np_other_idx]))

    from scipy.spatial import cKDTree
    obj_tree = cKDTree(np_other_xy)
    list_neighbors = obj_tree.query_ball_point(np_stromal_xy, r=float_radius_px)

    np_drop_local = np.array([len(ns) > 0 for ns in list_neighbors], dtype=bool)
    if not np_drop_local.any():
        return all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, 0

    np_drop_idx = np_stromal_idx[np_drop_local]
    np_keep_mask = np.ones(len(all_x), dtype=bool)
    np_keep_mask[np_drop_idx] = False

    return (
        all_x[np_keep_mask],
        all_y[np_keep_mask],
        all_conf[np_keep_mask],
        all_cls[np_keep_mask],
        all_x0[np_keep_mask],
        all_y0[np_keep_mask],
        all_x1[np_keep_mask],
        all_y1[np_keep_mask],
        int(np_drop_local.sum()),
    )


def run_detection(task_id: str, slide_id: str, roi_polygons: Optional[list], tissue_type: str):
    """
    text text — text DetectionWorker.run()text text text:
    1. text text → text text text
    2. text I/O text (ThreadPoolExecutor)
    3. text GPU text (8text)
    """
    list_cleanup_on_cancel = []
    try:
        import torch
        import numpy as np
        import cv2

        info = slide_manager.get(slide_id)
        if not info:
            update_task(task_id, status="error", error="text text text text")
            return

        # ── text AI text text (text/ROI text — text text text) ──
        cache_path = get_ai_cache_path(info.file_path, tissue_type)
        list_cleanup_on_cancel.append(cache_path)
        if cache_path.exists():
            try:
                update_task(task_id, status="running", progress=10,
                            status_msg=f"Loading cached AI result: {cache_path.name}")
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                cached, bool_rewrite_compact_cache = _compact_cached_result(cached)
                cached_cells = cached.get("cells") or []
                if cached_cells and not _cell_has_bbox(cached_cells[0]):
                    raise ValueError("stale cache missing bbox")
                if bool_rewrite_compact_cache:
                    try:
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            json.dump(cached, f, separators=(',', ':'))
                    except Exception as e:
                        print(f"Compact cache rewrite failed: {e}")
                # text hit text DB text text text auto_ai text text text text text.
                # (text text DB text text text slide doc text text text text.)
                # text — text set text text text.
                from app import slide_store
                slide_store.mark_ai_result_threadsafe(info.file_path, "Quanti HE", tissue_type)
                update_task(task_id, status="completed", progress=100,
                            status_msg=f"Loaded cached result ({cached.get('total_cells', 0)} cells)",
                            result=cached)
                return
            except Exception as e:
                import traceback
                print(f"Cache load failed, running fresh inference: {e}\n{traceback.format_exc()}")

        update_task(task_id, status="running", progress=1,
                    status_msg="Starting detection...")

        # ── text text ──
        from ai.quanti_he import CLASS_NAMES, CLASS_COLORS
        from ai.yolo_postprocess import non_max_suppression
        from ai.nets import nn as yolo_nn

        update_task(task_id, progress=1, status_msg="Loading detection model...")

        model_path = Path(settings.MODEL_DIR) / "HnE_detection.pt"
        if not model_path.exists():
            update_task(task_id, status="error", error=f"text text text: {model_path}")
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        num_classes = 6
        model = yolo_nn.yolo_v11_m(num_classes).to(device)
        checkpoint = torch.load(str(model_path), map_location=device, weights_only=False)
        model.load_state_dict(checkpoint['model_state_dict'])
        model.eval()

        update_task(task_id, progress=3, status_msg="Detection model loaded")

        # ── text (text DetectionWorkertext text) ──
        slide = info.slide
        slide_path = info.file_path
        width, height = info.dimensions
        image_size = 1024
        output_mpp = 0.5
        origin_mpp = info.mpp
        original_size = int(image_size * output_mpp / origin_mpp)

        BATCH_SIZE = 8
        IO_WORKERS = min(max(2, os.cpu_count() or 4), 8)
        PREFETCH_BATCHES = 3

        class_thresholds = {
            0: 0.01, 1: 0.01, 2: 0.01,
            3: 0.01, 4: 0.01, 5: 0.01,
        }

        # ── text text (text text) ──
        update_task(task_id, progress=4, status_msg="text text text text...")
        thumb_mask = create_tissue_mask(slide, icc_transform=info.icc_transform)
        update_task(task_id, progress=5)

        # ── Pre-scan: text text text ──
        valid_patch_list = []
        for pr in range(width // image_size - 1):
            for pc in range(height // image_size - 1):
                mx = (pr * image_size) // 64
                my = (pc * image_size) // 64
                if np.sum(thumb_mask[my:my + image_size // 64,
                                     mx:mx + image_size // 64]) == 0:
                    continue
                px, py = pr * image_size, pc * image_size
                # ROI text (text text)
                if roi_polygons:
                    cx, cy = px + image_size // 2, py + image_size // 2
                    in_roi = any(
                        min(p[0] for p in poly) <= cx <= max(p[0] for p in poly) and
                        min(p[1] for p in poly) <= cy <= max(p[1] for p in poly)
                        for poly in roi_polygons
                    )
                    if not in_roi:
                        continue
                valid_patch_list.append((px, py))

        n_valid = len(valid_patch_list)
        update_task(task_id, progress=6, status_msg=f"text text {n_valid}text text")

        if n_valid == 0:
            update_task(task_id, status="completed", progress=100, result={
                "total_cells": 0, "cells": [],
                "class_names": {str(k): v for k, v in CLASS_NAMES.items()},
                "class_colors": {str(k): v for k, v in CLASS_COLORS.items()},
            })
            return

        # ── numpy text text (text text: list-of-dicts text numpy text) ──
        chunks_x, chunks_y, chunks_cls, chunks_conf = [], [], [], []
        chunks_x0, chunks_y0, chunks_x1, chunks_y1 = [], [], [], []
        detected_count = 0
        processed_valid = 0

        # ── I/O → text text text (text text OpenSlide) ──
        icc_tf = info.icc_transform
        def _read_patch_tensor(patch_x, patch_y):
            patch = None
            patch_rgb = None
            try:
                wait_if_viewer_busy()
                local_slide = get_thread_slide(slide_id, slide_path)

                patch = local_slide.read_region((patch_x, patch_y), 0, (image_size, image_size))
                patch_rgb = patch.convert('RGB')
                if icc_tf is not None:
                    from PIL import ImageCms
                    ImageCms.applyTransform(patch_rgb, icc_tf, inPlace=True)
                patch_np = np.asarray(patch_rgb)
                patch_resized = cv2.resize(patch_np, (512, 512))
                return torch.from_numpy(patch_resized.copy()).permute(2, 0, 1).float() / 255.0
            except Exception as e:
                return None
            finally:
                if patch_rgb is not None:
                    try:
                        patch_rgb.close()
                    except Exception:
                        pass
                if patch is not None:
                    try:
                        patch.close()
                    except Exception:
                        pass

        # ── text GPU text text (text _infer_batchtext text) ──
        def _infer_batch(batch_coords, batch_tensors):
            bx, by, bcls, bconf = [], [], [], []
            bx0, by0, bx1, by1 = [], [], [], []
            try:
                batch = torch.stack(batch_tensors).to(device)
                with torch.no_grad():
                    if device == "cuda":
                        with torch.amp.autocast('cuda'):
                            preds = model(batch)
                    else:
                        preds = model(batch)

                results = non_max_suppression(
                    preds, confidence_threshold=0.01,
                    iou_threshold=0.3, class_thresholds=class_thresholds,
                )

                coord_scale = image_size / 512  # = 2.0
                for i, (sx, sy) in enumerate(batch_coords):
                    if i >= len(results) or len(results[i]) == 0:
                        continue
                    det = results[i]
                    xyxy = det[:, :4]
                    cx_np = ((xyxy[:, 0] + xyxy[:, 2]) / 2 * coord_scale + sx).cpu().numpy().astype(np.float32)
                    cy_np = ((xyxy[:, 1] + xyxy[:, 3]) / 2 * coord_scale + sy).cpu().numpy().astype(np.float32)
                    x0_np = (xyxy[:, 0] * coord_scale + sx).cpu().numpy().astype(np.float32)
                    y0_np = (xyxy[:, 1] * coord_scale + sy).cpu().numpy().astype(np.float32)
                    x1_np = (xyxy[:, 2] * coord_scale + sx).cpu().numpy().astype(np.float32)
                    y1_np = (xyxy[:, 3] * coord_scale + sy).cpu().numpy().astype(np.float32)
                    cls_np = det[:, 5].cpu().numpy().astype(np.int32)
                    conf_np = det[:, 4].cpu().numpy().astype(np.float32)
                    if len(cx_np) > 0:
                        bx.append(cx_np)
                        by.append(cy_np)
                        bx0.append(x0_np)
                        by0.append(y0_np)
                        bx1.append(x1_np)
                        by1.append(y1_np)
                        bcls.append(cls_np)
                        bconf.append(conf_np)
            except Exception as e:
                import traceback
                print(f"Batch inference error: {e}\n{traceback.format_exc()}")

            if not bx:
                ef = np.empty(0, dtype=np.float32)
                ei = np.empty(0, dtype=np.int32)
                return ef, ef.copy(), ei, ef.copy(), ef.copy(), ef.copy(), ef.copy(), ef.copy()
            return (
                np.concatenate(bx),
                np.concatenate(by),
                np.concatenate(bcls),
                np.concatenate(bconf),
                np.concatenate(bx0),
                np.concatenate(by0),
                np.concatenate(bx1),
                np.concatenate(by1),
            )

        # ══════════════════════════════════════
        # text: I/O text → text GPU text
        # (text DetectionWorker._io_producer text text)
        # ══════════════════════════════════════
        prefetch_q = queue.Queue(maxsize=PREFETCH_BATCHES)
        producer_done = threading.Event()

        def _io_producer():
            try:
                with ThreadPoolExecutor(max_workers=IO_WORKERS) as pool:
                    pending = []
                    for px, py in valid_patch_list:
                        if is_cancel_requested(task_id):
                            break
                        future = pool.submit(_read_patch_tensor, px, py)
                        pending.append((px, py, future))

                        if len(pending) >= BATCH_SIZE:
                            coords, tensors = [], []
                            for bpx, bpy, f in pending:
                                t = f.result(timeout=60)
                                if t is not None:
                                    coords.append((bpx, bpy))
                                    tensors.append(t)
                            if coords:
                                prefetch_q.put((coords, tensors, len(pending)), timeout=30)
                            pending.clear()

                    # text text
                    if pending and not is_cancel_requested(task_id):
                        coords, tensors = [], []
                        for bpx, bpy, f in pending:
                            t = f.result(timeout=60)
                            if t is not None:
                                coords.append((bpx, bpy))
                                tensors.append(t)
                        if coords:
                            prefetch_q.put((coords, tensors, len(pending)), timeout=30)
            except Exception as e:
                print(f"I/O producer error: {e}")
            finally:
                producer_done.set()
                prefetch_q.put(None)  # sentinel

        producer_thread = threading.Thread(target=_io_producer, daemon=True)
        producer_thread.start()

        # ── GPU text text ──
        while True:
            check_cancel(task_id)
            try:
                item = prefetch_q.get(timeout=120)
            except queue.Empty:
                if producer_done.is_set():
                    break
                continue

            if item is None:
                break

            batch_coords, batch_tensors, patch_count = item
            bx, by, bcls, bconf, bx0, by0, bx1, by1 = _infer_batch(batch_coords, batch_tensors)
            k = len(bx)
            if k > 0:
                chunks_x.append(bx)
                chunks_y.append(by)
                chunks_cls.append(bcls)
                chunks_conf.append(bconf)
                chunks_x0.append(bx0)
                chunks_y0.append(by0)
                chunks_x1.append(bx1)
                chunks_y1.append(by1)
                detected_count += k

            processed_valid += patch_count
            pct = int(5 + (processed_valid / n_valid) * 45)  # 5~50%
            update_task(task_id, progress=min(pct, 50),
                        status_msg=f"Detection: Patch {processed_valid}/{n_valid} | Cells: {detected_count}")

        producer_thread.join(timeout=10)

        # ── text text ──
        if chunks_x:
            all_x = np.concatenate(chunks_x)
            all_y = np.concatenate(chunks_y)
            all_cls = np.concatenate(chunks_cls)
            all_conf = np.concatenate(chunks_conf)
            all_x0 = np.concatenate(chunks_x0)
            all_y0 = np.concatenate(chunks_y0)
            all_x1 = np.concatenate(chunks_x1)
            all_y1 = np.concatenate(chunks_y1)
        else:
            all_x = all_y = all_conf = np.empty(0, dtype=np.float32)
            all_x0 = all_y0 = all_x1 = all_y1 = np.empty(0, dtype=np.float32)
            all_cls = np.empty(0, dtype=np.int32)

        check_cancel(task_id)

        # ── Stromal cell text text: text text conf >= 0.1 text text text text Stromal text ──
        all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, int_stromal_dropped = (
            _suppress_stromal_when_others_present(
                all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, info.mpp
            )
        )
        if int_stromal_dropped > 0:
            print(f"[detection] suppressed {int_stromal_dropped} Stromal cells overlapping other classes")

        update_task(task_id, progress=50,
                    status_msg=f"Detection complete: {len(all_x)} cells")

        # ── Epithelial text (Breast/Stomachtext) ──
        seg_data = None
        auto_classify = tissue_type in ("Breast", "Stomach")
        if auto_classify and len(all_cls) > 0:
            epithelial_count = int(np.sum(all_cls == 1))
            if epithelial_count > 0:
                update_task(task_id, progress=52,
                            status_msg=f"Epithelial reclassification starting... ({epithelial_count} cells)")
                seg_data = run_epithelial_classification(
                    task_id, slide, slide_path, info, all_x, all_y, all_cls,
                    tissue_type, roi_polygons, device,
                )
            else:
                update_task(task_id, progress=98,
                            status_msg="No Epithelial cells found, skipping reclassification")
        elif not auto_classify:
            update_task(task_id, progress=98,
                        status_msg="Tissue type 'Other' — skipping reclassification")

        n_cells = len(all_x)
        all_cells = [
            [
                round(float(all_x[i]), 2),
                round(float(all_y[i]), 2),
                int(all_cls[i]),
                round(float(all_conf[i]), 4),
                round(float(all_x0[i]), 2),
                round(float(all_y0[i]), 2),
                round(float(all_x1[i]), 2),
                round(float(all_y1[i]), 2),
            ]
            for i in range(n_cells)
        ]

        result = {
            "total_cells": n_cells,
            "cells": all_cells,
            "class_names": {str(k): v for k, v in CLASS_NAMES.items()},
            "class_colors": {str(k): v for k, v in CLASS_COLORS.items()},
            "seg_data": seg_data,
        }

        check_cancel(task_id)
        # ── text text(text text)text text text text ──
        if roi_polygons is None:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, separators=(',', ':'))
                print(f"AI result cached: {cache_path}")
                from app import slide_store
                slide_store.mark_ai_result_threadsafe(info.file_path, "Quanti HE", tissue_type)
            except Exception as e:
                import traceback
                print(f"Cache save failed: {e}\n{traceback.format_exc()}")

        update_task(task_id, status="completed", progress=100, result=result)

    except TaskCancelled:
        cleanup_cache_paths(list_cleanup_on_cancel)
        update_task(task_id, status="cancelled", progress=0,
                    status_msg="Cancelled by user", error=None)
        print(f"[cancel] run_detection cancelled task={task_id}")
    except Exception as e:
        import traceback
        update_task(task_id, status="error", error=f"{e}\n{traceback.format_exc()}")


def run_epithelial_classification(task_id, slide, slide_path, info, all_x, all_y, all_cls,
                                  tissue_type, roi_polygons, device):
    """
    Epithelial text: WSI Segmentation → Epithelial(1) → Tumor(6) / Benign(7)
    text DetectionWorker._run_epithelial_classificationtext text text
    all_clstext in-placetext text.
    Returns: seg_data dict (seg_class_names, overlays as base64, thumbnail) or None
    """
    import numpy as np
    import torch

    try:
        from ai.epithelial_classifier import WSISegmentationModel

        # Segmentation text text
        if tissue_type == "Breast":
            seg_model_path = Path(settings.MODEL_DIR) / "HnE_BR_segmentation.pt"
        elif tissue_type == "Stomach":
            seg_model_path = Path(settings.MODEL_DIR) / "HnE_ST_segmentation.pt"
        else:
            return

        if not seg_model_path.exists():
            update_task(task_id, status_msg=f"Segmentation model not found: {seg_model_path}")
            return

        update_task(task_id, progress=52,
                    status_msg="Loading segmentation model...")

        seg_model = WSISegmentationModel(
            model_path=str(seg_model_path),
            model_mpp=1.0,
            output_mpp=4.0,
            device=device,
        )

        # ROI bounds text
        roi_bounds = None
        if roi_polygons:
            min_x = min(p[0] for poly in roi_polygons for p in poly)
            min_y = min(p[1] for poly in roi_polygons for p in poly)
            max_x = max(p[0] for poly in roi_polygons for p in poly)
            max_y = max(p[1] for poly in roi_polygons for p in poly)
            roi_bounds = (int(min_x), int(min_y), int(max_x), int(max_y))

        update_task(task_id, progress=55,
                    status_msg="Running WSI Segmentation...")

        def progress_cb(pct):
            # 55~90% text
            update_task(task_id, progress=55 + int(pct * 0.35),
                        status_msg=f"WSI Segmentation... {int(pct)}%")

        prediction_mask, metadata = seg_model.predict_wsi(
            slide,
            patch_size=512,
            overlap_ratio=0.4,
            batch_size=8,
            progress_callback=progress_cb,
            roi_bounds=roi_bounds,
            image_path=slide_path,
            icc_transform=info.icc_transform,
        )

        update_task(task_id, progress=92,
                    status_msg="Reclassifying Epithelial cells...")

        # ── Epithelial text text mask text text ──
        wsi_mpp = info.mpp
        output_mpp = seg_model.output_mpp
        scale_factor = wsi_mpp / output_mpp
        region_offset_x = metadata.get('region_offset', (0, 0))[0]
        region_offset_y = metadata.get('region_offset', (0, 0))[1]

        epi_indices = np.where(all_cls == 1)[0]
        if len(epi_indices) == 0:
            return

        epi_xs = all_x[epi_indices]
        epi_ys = all_y[epi_indices]
        mxs = ((epi_xs - region_offset_x) * scale_factor).astype(np.int32)
        mys = ((epi_ys - region_offset_y) * scale_factor).astype(np.int32)
        h, w = prediction_mask.shape
        valid = (mxs >= 0) & (mxs < w) & (mys >= 0) & (mys < h)
        seg_vals = np.zeros(len(epi_indices), dtype=np.int32)
        seg_vals[valid] = prediction_mask[mys[valid], mxs[valid]]

        # ── Connected component text (text text) ──
        # text connected component (8-neighbor) text tumor text text 10% text
        # text component text text epithelial text Tumor text text text text.
        # benign text text tumor text "text"text tumor text text text text text
        # text text, text text text text text segmentation text text.
        # from scipy import ndimage as ndi
        # TUMOR_RATIO_THRESHOLD = 0.1
        # epi_region = np.isin(prediction_mask, [2, 3]).astype(np.uint8)
        # labeled_mask, num_components = ndi.label(epi_region, structure=np.ones((3, 3), dtype=np.int8))
        #
        # flat_label = labeled_mask.ravel()
        # flat_mask = prediction_mask.ravel().astype(np.int32)
        # n_bins = num_components + 1
        # tumor_counts = np.bincount(flat_label, weights=(flat_mask == 3), minlength=n_bins)
        # total_counts = np.bincount(flat_label, weights=np.isin(flat_mask, [2, 3]).astype(float), minlength=n_bins)
        # with np.errstate(invalid='ignore', divide='ignore'):
        #     tumor_ratio = np.where(total_counts > 0, tumor_counts / total_counts, 0.0)
        # comp_class_arr = np.where(tumor_ratio >= TUMOR_RATIO_THRESHOLD, 3, 2).astype(np.int32)
        # comp_class_arr[0] = 0  # background
        #
        # lh, lw = labeled_mask.shape
        # lvalid = (mxs >= 0) & (mxs < lw) & (mys >= 0) & (mys < lh)
        # comp_ids = np.zeros(len(epi_indices), dtype=np.int32)
        # comp_ids[lvalid] = labeled_mask[mys[lvalid], mxs[lvalid]]
        # update_mask = comp_ids > 0
        # seg_vals[update_mask] = comp_class_arr[comp_ids[update_mask]]

        # cls_arr in-place text: text text text text
        #   prediction_mask text 2(Benign) → 7, text text(0/1/3, text text·other·tumor) → 6(Tumor)
        all_cls[epi_indices] = np.where(seg_vals == 2, 7, 6).astype(np.int32)

        update_task(task_id, progress=98,
                    status_msg=f"Epithelial reclassification complete ({len(epi_indices)} cells)")

        # ── text + text text text (text text) ──
        seg_data = build_seg_overlays(slide, prediction_mask, metadata,
                                      seg_model.class_names, roi_bounds,
                                      icc_transform=info.icc_transform)

        del seg_model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return seg_data

    except Exception as e:
        import traceback
        print(f"Epithelial reclassification failed: {e}\n{traceback.format_exc()}")
        update_task(task_id, progress=98,
                    status_msg=f"Reclassification failed, using original results: {e}")
        return None


def build_seg_overlays(slide, prediction_mask, metadata, class_names, roi_bounds, icc_transform=None):
    """
    text text(prob_map)text text text text text text base64 text.
    text _create_spatial_heatmap_tabtext text: jet colormap + alpha=0.75 on probability maps.
    """
    import numpy as np
    import cv2
    import base64
    import io
    from PIL import Image

    try:
        # text text (ROI text text text)
        THUMB_SIZE = 800
        sw, sh = slide.dimensions
        if roi_bounds:
            x0, y0, x1, y1 = roi_bounds
        else:
            x0, y0, x1, y1 = 0, 0, sw, sh
        rw, rh = x1 - x0, y1 - y0

        # text text text
        if rw >= rh:
            tw = THUMB_SIZE
            th = max(1, int(THUMB_SIZE * rh / rw))
        else:
            th = THUMB_SIZE
            tw = max(1, int(THUMB_SIZE * rw / rh))

        # text text
        if roi_bounds:
            # ROI: text text text read_region → text text
            best_level = slide.get_best_level_for_downsample(max(rw, rh) / THUMB_SIZE)
            ds = slide.level_downsamples[best_level]
            read_w = int(rw / ds)
            read_h = int(rh / ds)
            region = slide.read_region((x0, y0), best_level, (read_w, read_h))
            thumb_rgb = region.convert('RGB')
        else:
            thumb = slide.get_thumbnail((THUMB_SIZE, THUMB_SIZE))
            thumb_rgb = thumb.convert('RGB')
        if icc_transform is not None:
            from PIL import ImageCms
            ImageCms.applyTransform(thumb_rgb, icc_transform, inPlace=True)
        thumb_np = np.array(thumb_rgb)
        thumb_resized = cv2.resize(thumb_np, (tw, th))

        # text → base64 JPEG
        _, thumb_buf = cv2.imencode('.jpeg', cv2.cvtColor(thumb_resized, cv2.COLOR_RGB2BGR),
                                     [cv2.IMWRITE_JPEG_QUALITY, 85])
        thumb_b64 = base64.b64encode(thumb_buf.tobytes()).decode('ascii')

        # ── text text text (text text) ──
        # metadata['prob_map'] = (num_classes, H, W) softmax probabilities
        # predict_wsitext roi_boundstext 10% text text mask/prob_map text ≠ roi_bounds
        # → roi_boundstext text text crop text
        prob_map = metadata.get('prob_map')
        region_offset = metadata.get('region_offset', (0, 0))
        wsi_mpp = metadata.get('wsi_mpp', 0.25)
        output_mpp = metadata.get('output_mpp', 8.0)
        mpp_ratio = output_mpp / wsi_mpp  # mask 1px = WSI mpp_ratio px

        # mask/prob_maptext roi_boundstext text crop text text
        mask_h, mask_w = prediction_mask.shape
        if roi_bounds:
            # roi_bounds(WSI text) → mask text
            crop_mx0 = max(0, int((x0 - region_offset[0]) / mpp_ratio))
            crop_my0 = max(0, int((y0 - region_offset[1]) / mpp_ratio))
            crop_mx1 = min(mask_w, int((x1 - region_offset[0]) / mpp_ratio))
            crop_my1 = min(mask_h, int((y1 - region_offset[1]) / mpp_ratio))
        else:
            crop_mx0, crop_my0 = 0, 0
            crop_mx1, crop_my1 = mask_w, mask_h

        overlays = {}
        num_classes = len(class_names) if class_names else int(prediction_mask.max()) + 1

        for cls_id in range(1, num_classes):  # 0=Background text
            cls_name = class_names[cls_id] if class_names and cls_id < len(class_names) else f'Class_{cls_id}'

            if prob_map is not None and cls_id < prob_map.shape[0]:
                # roi text crop text text text bilinear text
                cropped = prob_map[cls_id][crop_my0:crop_my1, crop_mx0:crop_mx1].astype(np.float32)
                prob_resized = cv2.resize(cropped, (tw, th),
                                          interpolation=cv2.INTER_LINEAR)
            else:
                # fallback: argmax text crop → text + blur
                cropped = prediction_mask[crop_my0:crop_my1, crop_mx0:crop_mx1].astype(np.uint8)
                mask_resized = cv2.resize(cropped, (tw, th),
                                           interpolation=cv2.INTER_NEAREST)
                prob_resized = cv2.GaussianBlur(
                    (mask_resized == cls_id).astype(np.float32), (7, 7), 2.0)

            # jet colormap text (text: cmap='jet', alpha=0.75, vmin=0, vmax=1)
            cls_norm = (np.clip(prob_resized, 0, 1) * 255).astype(np.uint8)
            cls_jet = cv2.applyColorMap(cls_norm, cv2.COLORMAP_JET)
            # alpha: text text (0.75 text)
            alpha = (np.clip(prob_resized, 0, 1) * 0.75 * 255).astype(np.uint8)
            cls_rgba = np.dstack([cv2.cvtColor(cls_jet, cv2.COLOR_BGR2RGB), alpha])

            img = Image.fromarray(cls_rgba, 'RGBA')
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            overlays[cls_name] = base64.b64encode(buf.getvalue()).decode('ascii')

        return {
            'thumbnail': thumb_b64,
            'overlays': overlays,
            'class_names': class_names[1:] if class_names else [],  # Background text
            'width': tw,
            'height': th,
        }
    except Exception as e:
        import traceback
        print(f"Seg overlay generation failed: {e}\n{traceback.format_exc()}")
        return None
