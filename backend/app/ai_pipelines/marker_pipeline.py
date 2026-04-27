"""PD-Score / Precise-IHC 공용 marker detection 파이프라인 + wrapper.

routers/ai.py 의 모놀리스에서 분리. PD-Score 와 Precise-IHC 가 동일한 YOLOv11m
검출 + 스코어 계산 흐름을 공유하므로 한 함수에서 처리하고 wrapper 두 개가
모델/스코어 함수만 다르게 주입한다.

임계값은 SaMD 인허가 재현성을 위해 모델별 고정 — 사용자 조절 금지.
- PD-Score: 0.1
- Precise-IHC HER2: 0.5
- Precise-IHC ER_PR / KI_67: 0.3
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
from app.ai_pipelines.scoring import (
    PD_SCORE_CONFIG,
    PRECISE_IHC_CONFIG,
    compute_allred_score,
    compute_her2_score,
    compute_ki67_score,
    compute_pd_score,
)
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


def run_marker_detection_pipeline(
    task_id, slide_id, roi_polygons,
    dict_config, cache_path,
    score_fn, score_key,
    extra_fields, log_label,
    str_variant: str = "",
    float_score_conf_threshold: float = 0.5,
):
    """
    YOLOv11m 기반 marker detection 공용 파이프라인.
    PD-Score / Precise-IHC 가 공유.
    임계값은 모델별로 고정 — 인허가(SaMD) 재현성을 위해 사용자 조절 금지.
      - PD-Score (Stomach/Lung): 0.1
      - Precise-IHC (HER2/ER_PR): 0.5
    각 wrapper 에서 명시적으로 전달한다.
    """
    list_cleanup_on_cancel = [cache_path]
    try:
        import torch
        import numpy as np
        import cv2

        info = slide_manager.get(slide_id)
        if not info:
            update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
            return

        dict_class_names = dict_config["class_names"]
        dict_class_colors = dict_config["class_colors"]
        int_num_classes = dict_config["num_classes"]
        list_exclude = dict_config.get("exclude_classes") or []

        # ── 캐시 확인 ──
        if cache_path.exists():
            try:
                update_task(task_id, status="running", progress=10,
                            status_msg=f"Loading cached {log_label}: {cache_path.name}")
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)

                # 레거시 캐시(score_conf_threshold 필드 없음 또는 값이 다른 경우)는
                # cells 로부터 현재 임계값으로 score 재계산.
                float_cached_thr = cached.get("score_conf_threshold")
                if float_cached_thr != float_score_conf_threshold:
                    list_cached_cells = cached.get("cells") or []
                    if list_cached_cells:
                        arr_cls = np.array(
                            [c.get("class_id", 0) for c in list_cached_cells],
                            dtype=np.int32,
                        )
                        arr_conf = np.array(
                            [c.get("confidence", 0.0) for c in list_cached_cells],
                            dtype=np.float32,
                        )
                        cls_for_score = arr_cls[arr_conf >= float_score_conf_threshold]
                    else:
                        cls_for_score = np.empty(0, dtype=np.int32)
                    cached[score_key] = score_fn(cls_for_score)
                    cached["score_conf_threshold"] = float_score_conf_threshold
                    try:
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            json.dump(cached, f)
                        print(f"{log_label} cached score recomputed @ conf>={float_score_conf_threshold}")
                    except Exception as e:
                        print(f"{log_label} cache rewrite failed: {e}")

                # 캐시 hit 이어도 DB 플래그가 비어 있으면 auto_ai 가 매 사이클 다시 끌어옴.
                # 멱등 ($addToSet) 이라 중복 호출 안전.
                from app import slide_store
                str_model_key_cache = log_label.split("/")[0]
                slide_store.mark_ai_result_threadsafe(info.file_path, str_model_key_cache, str_variant)
                update_task(task_id, status="completed", progress=100,
                            status_msg=f"Loaded cached result ({cached.get('total_cells', 0)} cells)",
                            result=cached)
                return
            except Exception as e:
                import traceback
                print(f"{log_label} cache load failed: {e}\n{traceback.format_exc()}")

        update_task(task_id, status="running", progress=1,
                    status_msg=f"Starting {log_label} detection...")

        # ── 모델 로드 ──
        from ai.detection import non_max_suppression
        from ai.nets import nn as yolo_nn

        model_path = Path(settings.MODEL_DIR) / dict_config["model_file"]
        if not model_path.exists():
            update_task(task_id, status="error", error=f"모델 파일 없음: {model_path}")
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = yolo_nn.yolo_v11_m(int_num_classes).to(device)
        checkpoint = torch.load(str(model_path), map_location=device, weights_only=False)

        # PDL1 체크포인트는 DFL 채널수가 4 (기본 16 대신). head 를 재구성하여 shape 맞춤.
        state_dict = checkpoint['model_state_dict']
        dfl_weight = state_dict.get('head.dfl.conv.weight')
        if dfl_weight is not None and dfl_weight.shape[1] != model.head.ch:
            int_ch_ckpt = int(dfl_weight.shape[1])
            update_task(task_id, status_msg=f"Rebuilding head with DFL ch={int_ch_ckpt}")
            head = model.head
            head.ch = int_ch_ckpt
            head.no = head.nc + head.ch * 4
            head.dfl = yolo_nn.DFL(head.ch).to(device)
            # box 브랜치의 마지막 Conv2d 만 out_channels 교체
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

        BATCH_SIZE = 8
        IO_WORKERS = min(max(2, os.cpu_count() or 4), 8)
        PREFETCH_BATCHES = 3

        class_thresholds = {i: 0.01 for i in range(int_num_classes)}

        # ── 조직 마스크 ──
        update_task(task_id, progress=4, status_msg="조직 마스크 생성 중...")
        thumb_mask = create_tissue_mask(slide, icc_transform=info.icc_transform)
        update_task(task_id, progress=5)

        # ── 유효 패치 수집 ──
        valid_patch_list = []
        for pr in range(width // image_size - 1):
            for pc in range(height // image_size - 1):
                mx = (pr * image_size) // 64
                my = (pc * image_size) // 64
                if np.sum(thumb_mask[my:my + image_size // 64,
                                     mx:mx + image_size // 64]) == 0:
                    continue
                px, py = pr * image_size, pc * image_size
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
        update_task(task_id, progress=6, status_msg=f"유효 패치 {n_valid}개 발견")

        if n_valid == 0:
            empty_score = score_fn(np.empty(0, dtype=np.int32))
            empty_result = {
                "total_cells": 0, "cells": [],
                "class_names": {str(k): v for k, v in dict_class_names.items() if k not in list_exclude},
                "class_colors": {str(k): v for k, v in dict_class_colors.items() if k not in list_exclude},
                "score_conf_threshold": float_score_conf_threshold,
                score_key: empty_score,
                **(extra_fields or {}),
            }
            update_task(task_id, status="completed", progress=100, result=empty_result)
            return

        chunks_x, chunks_y, chunks_cls, chunks_conf = [], [], [], []
        detected_count = 0
        processed_valid = 0

        icc_tf = info.icc_transform
        def _read_patch_tensor(patch_x, patch_y):
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
            except Exception:
                return None

        def _infer_batch(batch_coords, batch_tensors):
            bx, by, bcls, bconf = [], [], [], []
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
                    cls_np = det[:, 5].cpu().numpy().astype(np.int32)
                    conf_np = det[:, 4].cpu().numpy().astype(np.float32)
                    if len(cx_np) > 0:
                        bx.append(cx_np)
                        by.append(cy_np)
                        bcls.append(cls_np)
                        bconf.append(conf_np)
            except Exception as e:
                import traceback
                print(f"{log_label} batch inference error: {e}\n{traceback.format_exc()}")

            if not bx:
                ef = np.empty(0, dtype=np.float32)
                ei = np.empty(0, dtype=np.int32)
                return ef, ef.copy(), ei, ef.copy()
            return np.concatenate(bx), np.concatenate(by), np.concatenate(bcls), np.concatenate(bconf)

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
            bx, by, bcls, bconf = _infer_batch(batch_coords, batch_tensors)
            k = len(bx)
            if k > 0:
                chunks_x.append(bx)
                chunks_y.append(by)
                chunks_cls.append(bcls)
                chunks_conf.append(bconf)
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
        else:
            all_x = all_y = all_conf = np.empty(0, dtype=np.float32)
            all_cls = np.empty(0, dtype=np.int32)

        # ── 표시 제외 클래스 필터링 (e.g. 'Other' 클래스) ──
        if list_exclude and len(all_cls) > 0:
            keep_mask = ~np.isin(all_cls, list_exclude)
            all_x = all_x[keep_mask]
            all_y = all_y[keep_mask]
            all_cls = all_cls[keep_mask]
            all_conf = all_conf[keep_mask]

        n_cells = len(all_x)
        update_task(task_id, progress=97,
                    status_msg=f"Computing {dict_config['score_type']} score...")

        all_cells = [
            {
                "x": float(all_x[i]),
                "y": float(all_y[i]),
                "confidence": float(all_conf[i]),
                "class_id": int(all_cls[i]),
                "class_name": dict_class_names.get(int(all_cls[i]), "Unknown"),
            }
            for i in range(n_cells)
        ]

        # Score 는 모델별 고정 confidence 임계값으로 계산 (PD=0.1, Precise-IHC=0.5).
        # SaMD 인허가 재현성을 위해 사용자 조절 불가.
        if len(all_conf) > 0:
            mask_score = all_conf >= float_score_conf_threshold
            cls_for_score = all_cls[mask_score]
        else:
            cls_for_score = all_cls
        score_dict = score_fn(cls_for_score)

        result = {
            "total_cells": n_cells,
            "cells": all_cells,
            "class_names": {str(k): v for k, v in dict_class_names.items() if k not in list_exclude},
            "class_colors": {str(k): v for k, v in dict_class_colors.items() if k not in list_exclude},
            "score_conf_threshold": float_score_conf_threshold,
            score_key: score_dict,
            **(extra_fields or {}),
        }

        check_cancel(task_id)
        if roi_polygons is None:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f)
                print(f"{log_label} result cached: {cache_path}")
                from app import slide_store
                # "Precise-IHC/HER2" → "Precise-IHC"
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
    """PD-Score 파이프라인 wrapper (공용 marker pipeline 호출)."""
    dict_config = PD_SCORE_CONFIG[tissue_type]
    info = slide_manager.get(slide_id)
    if not info:
        update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
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
        log_label="PD-Score",
        str_variant=tissue_type,
        float_score_conf_threshold=0.1,  # PD-L1 Stomach/Lung 고정 (SaMD 재현성)
    )


def run_precise_ihc(task_id, slide_id, roi_polygons, marker: str):
    """Precise-IHC 파이프라인 wrapper — HER2 / ER_PR / KI_67 지원."""
    if marker not in PRECISE_IHC_CONFIG:
        update_task(task_id, status="error", error=f"지원하지 않는 marker: {marker}")
        return
    dict_config = PRECISE_IHC_CONFIG[marker]
    info = slide_manager.get(slide_id)
    if not info:
        update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
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

    # Precise-IHC 고정 임계값 (SaMD 재현성): HER2=0.5, ER_PR/KI_67=0.3
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
        log_label=f"Precise-IHC/{marker}",
        str_variant=marker,
        float_score_conf_threshold=float_conf,
    )
