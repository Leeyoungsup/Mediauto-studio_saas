"""Quanti PD-L1 / Quanti IHC text marker detection text + wrapper.

routers/ai.py text text text. Quanti PD-L1 text Quanti IHC text text YOLOv11m
text + text text text text text text text wrapper text text
text/text text text text.

text SaMD text text text text text — text text text.
- Quanti PD-L1: 0.1
- Quanti IHC HER2: 0.5
- Quanti IHC ER_PR / KI_67: 0.3
"""

import json
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.ai_pipelines.cache_paths import (
    get_pd_score_cache_path,
    get_precise_ihc_cache_path,
)
from app.ai_pipelines.dedup import (
    DETECTION_PATCH_OVERLAP_UM,
    apply_global_cell_dedup,
    cache_has_current_detection_postprocess,
    patch_edge_keep_mask,
    processing_metadata,
    suppress_excluded_classes_overlapping_visible,
)
from app.ai_pipelines.patch_reader import AIPatchReader
from app.ai_pipelines.patch_coordinates import patch_coordinate_metadata, validate_patch_coordinate_cache
from ai.quanti_ihc import (
    PRECISE_IHC_CONFIG,
    compute_allred_score,
    compute_her2_score,
    compute_ki67_score,
)
from ai.quanti_pd_l1 import PD_SCORE_CONFIG, compute_pd_score
from app.ai_pipelines.task_state import (
    TaskCancelled,
    check_cancel,
    cleanup_cache_paths,
    is_cancel_requested,
    update_task,
)
from app.ai_pipelines.tissue_mask import build_valid_patch_list
from app.config import settings
from app.slide_manager import slide_manager
from app.tile_generator import slide_source_signature, source_signature_matches


def marker_model_runtime_metadata(dict_config: dict) -> dict:
    """Return the cache identity for a marker model architecture and weights."""
    str_model_arch = str(dict_config.get("model_arch") or "yolo_v11_m")
    int_num_classes = int(dict_config["num_classes"])
    int_num_grades = int(dict_config.get("num_grades") or max(1, int_num_classes - 1))
    model_path = Path(settings.MODEL_DIR) / dict_config["model_file"]
    model_stat = model_path.stat()
    return {
        "architecture": str_model_arch,
        "num_grades": int_num_grades if str_model_arch == "yolo_v11_m_hierarchical" else None,
        "filename": model_path.name,
        "size": model_stat.st_size,
        "mtime_ns": model_stat.st_mtime_ns,
    }


def _compact_cell(cell: dict) -> dict:
    if isinstance(cell, (list, tuple)):
        return list(cell)
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
    if cell.get("hidden") or cell.get("exclude_from_score"):
        compact.extend([bool(cell.get("hidden")), bool(cell.get("exclude_from_score"))])
    return compact


def _cell_has_bbox(cell) -> bool:
    if isinstance(cell, (list, tuple)):
        return len(cell) >= 8 and all(isinstance(cell[i], (int, float)) for i in range(4, 8))
    if isinstance(cell, dict):
        return all(k in cell for k in ("x0", "y0", "x1", "y1"))
    return False


def _compact_result_payload(result: dict) -> dict:
    if not isinstance(result, dict):
        return result
    for key in ("cells", "excluded_cells"):
        cells = result.get(key)
        if isinstance(cells, list):
            result[key] = [_compact_cell(c) for c in cells if isinstance(c, (dict, list, tuple))]
    if isinstance(result.get("cells"), list):
        result["total_cells"] = len(result["cells"])
    return result


def _cell_class_id(cell) -> int:
    if isinstance(cell, (list, tuple)):
        return int(cell[2]) if len(cell) > 2 else 0
    if isinstance(cell, dict):
        return int(cell.get("class_id", 0))
    return 0


def _cell_confidence(cell) -> float:
    if isinstance(cell, (list, tuple)):
        return float(cell[3]) if len(cell) > 3 else 0.0
    if isinstance(cell, dict):
        return float(cell.get("confidence", 0.0))
    return 0.0


def run_marker_detection_pipeline(
    task_id, slide_id, roi_polygons,
    dict_config, cache_path,
    score_fn, score_key,
    extra_fields, log_label,
    str_variant: str = "",
    float_score_conf_threshold: float = 0.5,
):
    """
    YOLOv11m text marker detection text text.
    Quanti PD-L1 / Quanti IHC text text.
    text text text — text(SaMD) text text text text text.
      - Quanti PD-L1 (Stomach/Lung): 0.1
      - Quanti IHC (HER2/ER_PR): 0.5
    text wrapper text text text.
    """
    list_cleanup_on_cancel = [cache_path]
    try:
        import torch
        import numpy as np
        import cv2

        info = slide_manager.get(slide_id)
        if not info:
            update_task(task_id, status="error", error="Slide is not open")
            return

        dict_class_names = dict_config["class_names"]
        dict_class_colors = dict_config["class_colors"]
        int_num_classes = dict_config["num_classes"]
        list_exclude = dict_config.get("exclude_classes") or []
        list_nms_priority = [i for i in range(int_num_classes) if i not in list_exclude]
        str_model_arch = str(dict_config.get("model_arch") or "yolo_v11_m")
        int_num_grades = int(dict_config.get("num_grades") or max(1, int_num_classes - 1))
        model_path = Path(settings.MODEL_DIR) / dict_config["model_file"]
        if not model_path.exists():
            update_task(task_id, status="error", error=f"Model file not found: {model_path}")
            return
        dict_model_runtime = marker_model_runtime_metadata(dict_config)

        # ── text text ──
        if cache_path.exists():
            try:
                update_task(task_id, status="running", progress=10,
                            status_msg=f"Loading cached {log_label}: {cache_path.name}")
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)

                validate_patch_coordinate_cache(cached, info.file_path, cache_path)
                if not source_signature_matches(cached, info.slide, info.file_path):
                    raise ValueError("stale cache source mismatch")
                if list_exclude and "excluded_cells" not in cached:
                    raise ValueError("stale cache missing excluded_cells")
                if not cache_has_current_detection_postprocess(cached):
                    raise ValueError("stale cache missing 10um overlap/global dedup")
                # HER2 currently opts into a different head. Match the model
                # architecture and weights so an old flat-model cache cannot
                # mask a hierarchical-model test.
                if dict_config.get("model_arch") and cached.get("model_runtime") != dict_model_runtime:
                    raise ValueError("stale cache model architecture or weights mismatch")

                list_cached_before_compact = cached.get("cells") or []
                bool_object_cell_cache = bool(
                    list_cached_before_compact and isinstance(list_cached_before_compact[0], dict)
                )
                cached = _compact_result_payload(cached)
                cached_cells = cached.get("cells") or []
                if cached_cells and not _cell_has_bbox(cached_cells[0]):
                    raise ValueError("stale cache missing bbox")
                bool_rewrite_compact_cache = bool_object_cell_cache

                # text text(score_conf_threshold text text text text text text)text
                # cells text text text score text.
                float_cached_thr = cached.get("score_conf_threshold")
                if float_cached_thr != float_score_conf_threshold:
                    list_cached_cells = cached.get("cells") or []
                    if list_cached_cells:
                        arr_cls = np.array(
                            [_cell_class_id(c) for c in list_cached_cells],
                            dtype=np.int32,
                        )
                        arr_conf = np.array(
                            [_cell_confidence(c) for c in list_cached_cells],
                            dtype=np.float32,
                        )
                        cls_for_score = arr_cls[arr_conf >= float_score_conf_threshold]
                    else:
                        cls_for_score = np.empty(0, dtype=np.int32)
                    cached[score_key] = score_fn(cls_for_score)
                    cached["score_conf_threshold"] = float_score_conf_threshold
                    bool_rewrite_compact_cache = True

                if bool_rewrite_compact_cache:
                    try:
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            json.dump(cached, f, separators=(',', ':'))
                        print(f"{log_label} compact cache rewritten")
                    except Exception as e:
                        print(f"{log_label} cache rewrite failed: {e}")

                # text hit text DB text text text auto_ai text text text text text.
                # text ($addToSet) text text text text.
                from app import slide_store
                str_model_key_cache = log_label.split("/")[0]
                slide_store.mark_ai_result_threadsafe(info.file_path, str_model_key_cache, str_variant)
                update_task(task_id, status="completed", progress=100,
                            status_msg=f"Loaded cached result ({cached.get('total_cells', 0)} cells)",
                            result=cached)
                return
            except ValueError as e:
                print(f"{log_label} cache skipped: {e}")
            except Exception as e:
                import traceback
                print(f"{log_label} cache load failed: {e}\n{traceback.format_exc()}")

        update_task(task_id, status="running", progress=1,
                    status_msg=f"Starting {log_label} detection...")

        # ── text text ──
        from ai.yolo_postprocess import non_max_suppression
        from ai.nets import nn as yolo_nn

        device = "cuda" if torch.cuda.is_available() else "cpu"
        if str_model_arch == "yolo_v11_m_hierarchical":
            if int_num_classes != int_num_grades + 1:
                raise ValueError(
                    "Hierarchical model expects num_classes=num_grades+1; "
                    f"got num_classes={int_num_classes}, num_grades={int_num_grades}"
                )
            model = yolo_nn.yolo_v11_m_hierarchical(num_grades=int_num_grades).to(device)
        elif str_model_arch == "yolo_v11_m":
            model = yolo_nn.yolo_v11_m(int_num_classes).to(device)
        else:
            raise ValueError(f"Unsupported marker model architecture: {str_model_arch}")
        checkpoint = torch.load(str(model_path), map_location=device, weights_only=False)

        # PDL1 text DFL text 4 (text 16 text). head text text shape text.
        state_dict = checkpoint['model_state_dict']
        dfl_weight = state_dict.get('head.dfl.conv.weight')
        if dfl_weight is not None and dfl_weight.shape[1] != model.head.ch:
            int_ch_ckpt = int(dfl_weight.shape[1])
            update_task(task_id, status_msg=f"Rebuilding head with DFL ch={int_ch_ckpt}")
            head = model.head
            head.ch = int_ch_ckpt
            head.no = head.ch * 4 + int(getattr(head, "num_semantic_outputs", head.nc))
            head.dfl = yolo_nn.DFL(head.ch).to(device)
            # box text text Conv2d text out_channels text
            for seq in head.box:
                old = seq[-1]
                new_conv = torch.nn.Conv2d(
                    old.in_channels,
                    out_channels=4 * head.ch,
                    kernel_size=old.kernel_size,
                    stride=old.stride,
                    padding=old.padding,
                ).to(device)
                seq[-1] = new_conv

        model.load_state_dict(state_dict)
        model.eval()

        update_task(task_id, progress=3, status_msg=f"{log_label} model loaded")

        slide = info.slide
        slide_path = info.file_path
        width, height = info.dimensions
        image_size = 1024
        output_mpp = 0.5
        origin_mpp = info.mpp

        from app.cpu_layout import INT_AI
        BATCH_SIZE = 8
        IO_WORKERS = max(1, min(INT_AI, 4))
        PREFETCH_BATCHES = 3

        class_thresholds = {i: 0.01 for i in range(int_num_classes)}

        has_envelope = bool(getattr(slide, "data_envelope_rectangles", []))
        update_task(
            task_id,
            progress=4,
            status_msg="Using slide data envelopes..." if has_envelope else "Creating tissue mask...",
        )
        valid_patch_list, patch_source = build_valid_patch_list(
            slide,
            width,
            height,
            image_size,
            roi_polygons=roi_polygons,
            icc_transform=info.icc_transform,
            mpp=info.mpp,
            overlap_um=DETECTION_PATCH_OVERLAP_UM,
        )
        update_task(task_id, progress=5)

        n_valid = len(valid_patch_list)
        update_task(task_id, progress=6, status_msg=f"Queued {n_valid} {patch_source} patches")

        if n_valid == 0:
            empty_score = score_fn(np.empty(0, dtype=np.int32))
            empty_result = {
                "total_cells": 0, "cells": [],
                "excluded_cells": [],
                "class_names": {str(k): v for k, v in dict_class_names.items() if k not in list_exclude},
                "class_colors": {str(k): v for k, v in dict_class_colors.items() if k not in list_exclude},
                "score_conf_threshold": float_score_conf_threshold,
                "model_runtime": dict_model_runtime,
                score_key: empty_score,
                **(extra_fields or {}),
            }
            update_task(task_id, status="completed", progress=100, result=empty_result)
            return

        chunks_x, chunks_y, chunks_cls, chunks_conf = [], [], [], []
        chunks_x0, chunks_y0, chunks_x1, chunks_y1 = [], [], [], []
        detected_count = 0
        processed_valid = 0

        patch_reader = AIPatchReader(
            slide_id=slide_id,
            slide_path=slide_path,
            image_size=image_size,
            output_size=512,
            icc_transform=info.icc_transform,
        )

        def _read_patch_tensor(patch_x, patch_y):
            return patch_reader.read_tensor(patch_x, patch_y)

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
                    nms_priority_classes=list_nms_priority,
                )

                coord_scale = image_size / 512  # = 2.0
                for i, (sx, sy) in enumerate(batch_coords):
                    if i >= len(results) or len(results[i]) == 0:
                        continue
                    det = results[i]
                    xyxy = det[:, :4]
                    local_cx_np = ((xyxy[:, 0] + xyxy[:, 2]) / 2 * coord_scale).cpu().numpy().astype(np.float32)
                    local_cy_np = ((xyxy[:, 1] + xyxy[:, 3]) / 2 * coord_scale).cpu().numpy().astype(np.float32)
                    keep_edge = patch_edge_keep_mask(
                        local_cx_np, local_cy_np, sx, sy, width, height, image_size, info.mpp
                    )
                    if not keep_edge.any():
                        continue
                    keep_edge_t = torch.as_tensor(keep_edge, dtype=torch.bool, device=xyxy.device)
                    xyxy = xyxy[keep_edge_t]
                    local_cx_np = local_cx_np[keep_edge]
                    local_cy_np = local_cy_np[keep_edge]
                    cx_np = (local_cx_np + sx).astype(np.float32)
                    cy_np = (local_cy_np + sy).astype(np.float32)
                    x0_np = (xyxy[:, 0] * coord_scale + sx).cpu().numpy().astype(np.float32)
                    y0_np = (xyxy[:, 1] * coord_scale + sy).cpu().numpy().astype(np.float32)
                    x1_np = (xyxy[:, 2] * coord_scale + sx).cpu().numpy().astype(np.float32)
                    y1_np = (xyxy[:, 3] * coord_scale + sy).cpu().numpy().astype(np.float32)
                    cls_np = det[:, 5][keep_edge_t].cpu().numpy().astype(np.int32)
                    conf_np = det[:, 4][keep_edge_t].cpu().numpy().astype(np.float32)
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
                print(f"{log_label} batch inference error: {e}\n{traceback.format_exc()}")

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
                print(f"{log_label} I/O producer error: {e}")
            finally:
                producer_done.set()
                prefetch_q.put(None)

        producer_thread = threading.Thread(target=_io_producer, daemon=True)
        producer_thread.start()

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
            pct = int(5 + (processed_valid / n_valid) * 90)  # 5~95%
            update_task(task_id, progress=min(pct, 95),
                        status_msg=f"{log_label}: Patch {processed_valid}/{n_valid} | Cells: {detected_count}")

        producer_thread.join(timeout=10)

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

        all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, int_global_dedup_dropped = (
            apply_global_cell_dedup(
                all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, info.mpp,
                list_exclude=list_exclude,
            )
        )
        if int_global_dedup_dropped > 0:
            print(f"[{log_label}] global dedup dropped {int_global_dedup_dropped} overlap duplicate cells")

        # ── text text text text (e.g. 'Other' text) ──
        if list_exclude and len(all_cls) > 0:
            all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, int_excluded_overlap_dropped = (
                suppress_excluded_classes_overlapping_visible(
                    all_x, all_y, all_conf, all_cls, all_x0, all_y0, all_x1, all_y1, list_exclude
                )
            )
            if int_excluded_overlap_dropped > 0:
                print(f"[{log_label}] suppressed {int_excluded_overlap_dropped} excluded-class cells overlapping visible classes")

        excluded_cells = []
        if list_exclude and len(all_cls) > 0:
            exclude_mask = np.isin(all_cls, list_exclude)
            excluded_cells = [
                [
                    round(float(all_x[i]), 2),
                    round(float(all_y[i]), 2),
                    int(all_cls[i]),
                    round(float(all_conf[i]), 4),
                    round(float(all_x0[i]), 2),
                    round(float(all_y0[i]), 2),
                    round(float(all_x1[i]), 2),
                    round(float(all_y1[i]), 2),
                    True,
                    True,
                ]
                for i in np.where(exclude_mask)[0]
            ]
            keep_mask = ~exclude_mask
            all_x = all_x[keep_mask]
            all_y = all_y[keep_mask]
            all_cls = all_cls[keep_mask]
            all_conf = all_conf[keep_mask]
            all_x0 = all_x0[keep_mask]
            all_y0 = all_y0[keep_mask]
            all_x1 = all_x1[keep_mask]
            all_y1 = all_y1[keep_mask]

        n_cells = len(all_x)
        update_task(task_id, progress=97,
                    status_msg=f"Computing {dict_config['score_type']} score...")

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

        # Score text text text confidence text text (PD=0.1, Quanti IHC=0.5).
        # SaMD text text text text text text.
        if len(all_conf) > 0:
            mask_score = all_conf >= float_score_conf_threshold
            cls_for_score = all_cls[mask_score]
        else:
            cls_for_score = all_cls
        score_dict = score_fn(cls_for_score)

        result = {
            "total_cells": n_cells,
            "cells": all_cells,
            "excluded_cells": excluded_cells,
            "class_names": {str(k): v for k, v in dict_class_names.items() if k not in list_exclude},
            "class_colors": {str(k): v for k, v in dict_class_colors.items() if k not in list_exclude},
            "score_conf_threshold": float_score_conf_threshold,
            "model_runtime": dict_model_runtime,
            score_key: score_dict,
            "source": slide_source_signature(info.slide, info.file_path),
            **patch_coordinate_metadata(info.file_path),
            **processing_metadata(),
            **(extra_fields or {}),
        }

        check_cancel(task_id)
        if roi_polygons is None:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, separators=(',', ':'))
                print(f"{log_label} result cached: {cache_path}")
                from app import slide_store
                # "Quanti IHC/HER2" → "Quanti IHC"
                str_model_key = log_label.split("/")[0]
                slide_store.mark_ai_result_threadsafe(info.file_path, str_model_key, str_variant)
            except Exception as e:
                import traceback
                print(f"{log_label} cache save failed: {e}\n{traceback.format_exc()}")

        update_task(task_id, status="completed", progress=100, result=result)

    except TaskCancelled:
        cleanup_cache_paths(list_cleanup_on_cancel)
        update_task(task_id, status="cancelled", progress=0,
                    status_msg="Cancelled by user", error=None)
        print(f"[cancel] {log_label} cancelled task={task_id}")
    except Exception as e:
        import traceback
        update_task(task_id, status="error", error=f"{e}\n{traceback.format_exc()}")


def run_pd_score(task_id, slide_id, roi_polygons, tissue_type):
    """Quanti PD-L1 text wrapper (text marker pipeline text)."""
    dict_config = PD_SCORE_CONFIG[tissue_type]
    info = slide_manager.get(slide_id)
    if not info:
        update_task(task_id, status="error", error="Slide is not open")
        return
    cache_path = get_pd_score_cache_path(info.file_path, tissue_type)
    run_marker_detection_pipeline(
        task_id=task_id,
        slide_id=slide_id,
        roi_polygons=roi_polygons,
        dict_config=dict_config,
        cache_path=cache_path,
        score_fn=lambda all_cls: compute_pd_score(all_cls, tissue_type),
        score_key="pd_score",
        extra_fields={"tissue_type": tissue_type},
        log_label="Quanti PD-L1",
        str_variant=tissue_type,
        float_score_conf_threshold=0.1,  # PD-L1 Stomach/Lung text (SaMD text)
    )


def run_precise_ihc(task_id, slide_id, roi_polygons, marker: str):
    """Quanti IHC wrapper for scoring markers and breast cell-assistance models."""
    if marker not in PRECISE_IHC_CONFIG:
        update_task(task_id, status="error", error=f"Unsupported marker: {marker}")
        return
    dict_config = PRECISE_IHC_CONFIG[marker]
    info = slide_manager.get(slide_id)
    if not info:
        update_task(task_id, status="error", error="Slide is not open")
        return
    cache_path = get_precise_ihc_cache_path(info.file_path, marker)

    if marker == "HER2":
        score_fn = compute_her2_score
        score_key = "her2_score"
    elif marker == "ER_PR":
        score_fn = compute_allred_score
        score_key = "allred_score"
    elif marker == "KI_67":
        score_fn = compute_ki67_score
        score_key = "ki67_score"
    else:
        score_fn = lambda all_cls: {"score_type": marker, "score": 0.0}
        score_key = f"{marker.lower()}_score"

    # Quanti IHC text text (SaMD text): HER2=0.5, ER_PR/KI_67=0.3
    float_conf = 0.3 if marker in ("ER_PR", "KI_67") else 0.5

    run_marker_detection_pipeline(
        task_id=task_id,
        slide_id=slide_id,
        roi_polygons=roi_polygons,
        dict_config=dict_config,
        cache_path=cache_path,
        score_fn=score_fn,
        score_key=score_key,
        extra_fields={"marker": marker},
        log_label=f"Quanti IHC/{marker}",
        str_variant=marker,
        float_score_conf_threshold=float_conf,
    )
