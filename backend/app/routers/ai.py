"""
AI 분석 API — Detection / Segmentation
기존 ai/ 모듈의 병렬 I/O + 배치 GPU 추론 파이프라인을 그대로 사용
"""

import os
import sys
import json
import uuid
import queue
import threading
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Form, Query, Request
from fastapi.responses import JSONResponse, FileResponse

from app.audit import get_client_ip, log_audit_event
from app.auth import get_current_user, get_media_user, require_not_viewer
from app.config import settings
from app.slide_manager import slide_manager
from app.priority import wait_if_viewer_busy

# 기존 AI 코드 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Viewer 는 AI 기능 전면 차단 — 트리거/조회/결과 저장 모두 거부.
router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_not_viewer)])


async def _log_ai_analyze(
    request: Request,
    dict_user: dict,
    str_model: str,
    str_variant: str,
    str_slide_id: str,
    str_filename: str,
    str_task_id: str,
) -> None:
    """AI 분석 트리거 감사 로그 — 관리자 활동 추적용."""
    try:
        await log_audit_event(
            str_action="ai.analyze",
            str_user_id=str(dict_user.get("_id", "")),
            str_user_email=dict_user.get("str_login_id", ""),
            str_resource_type="slide",
            str_resource_id=str_slide_id,
            str_detail=f"{str_model}/{str_variant} on {str_filename}",
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
            dict_extra={
                "str_model": str_model,
                "str_variant": str_variant,
                "str_task_id": str_task_id,
                "str_slide_filename": str_filename,
            },
        )
    except Exception:
        pass

# Virtual stain 타일 전용 서브 라우터 — <img src> 용 ?mt= 티켓 허용.
# main.py 에서 같은 prefix("/api/ai") 로 별도 include 된다.
media_router = APIRouter(dependencies=[Depends(get_media_user)])

# AI 작업 상태 추적
_tasks = {}
_tasks_lock = threading.Lock()

# I/O 워커 스레드별 독립 OpenSlide 핸들은 app.thread_slide_pool 이 관리한다.
# generation 검증 + LRU eviction 포함 (SlideManager.close() 시 자동 무효화).
from app.thread_slide_pool import get_thread_slide as _get_thread_slide


def _update_task(task_id, **kwargs):
    with _tasks_lock:
        _tasks[task_id].update(kwargs)
    # 사용자 AI 진행 업데이트는 idle 타이머를 리셋 (auto_ 접두어 task 는 제외).
    # → 사용자가 추론 중이면 auto_ai 가 끼어들지 않음.
    if not task_id.startswith("auto_"):
        try:
            from app import auto_ai
            auto_ai.ping_ai_activity()
        except Exception:
            pass


class TaskCancelled(Exception):
    """사용자가 추론을 중단 요청했을 때 워커가 raise 하는 예외."""
    pass


def _is_cancel_requested(task_id: str) -> bool:
    with _tasks_lock:
        task = _tasks.get(task_id)
        return bool(task and task.get("cancel_requested"))


def _check_cancel(task_id: str) -> None:
    """체크포인트 — 취소 요청이 있으면 TaskCancelled 발생."""
    if _is_cancel_requested(task_id):
        raise TaskCancelled()


def _cleanup_cache_paths(list_paths) -> None:
    """취소 시 부분 저장된 캐시 파일/폴더 전부 삭제. 충돌 방지용."""
    import shutil
    for p in list_paths:
        if p is None:
            continue
        try:
            path_obj = Path(p)
            if path_obj.is_file():
                path_obj.unlink()
                print(f"[cancel] removed file: {path_obj}")
            elif path_obj.is_dir():
                shutil.rmtree(path_obj)
                print(f"[cancel] removed dir: {path_obj}")
        except Exception as e:
            print(f"[cancel] cleanup failed for {p}: {e}")


def _get_ai_cache_path(slide_path: str, tissue_type: str) -> Path:
    """
    HE-Fit 결과 캐시: ai_results/HE-Fit/{slide_stem}_HE-Fit_{tissue_type}.json
    레거시 경로 (ai_results/{slide_stem}_HE-Fit_{tissue_type}.json) 가 있으면
    새 위치로 자동 이동한다.
    """
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "HE-Fit"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    new_path = cache_dir / f"{p.stem}_HE-Fit_{tissue_type}.json"
    legacy_path = Path(settings.AI_RESULTS_DIR) / f"{p.stem}_HE-Fit_{tissue_type}.json"
    if not new_path.exists() and legacy_path.exists():
        try:
            legacy_path.replace(new_path)
        except Exception as e:
            print(f"[ai] HE-Fit legacy migration failed: {e}")
    return new_path


def _run_detection(task_id: str, slide_id: str, roi_polygons: Optional[list], tissue_type: str):
    """
    백그라운드 검출 — 기존 DetectionWorker.run()과 동일한 파이프라인:
    1. 조직 마스크 → 배경 패치 스킵
    2. 멀티스레드 I/O 프리페치 (ThreadPoolExecutor)
    3. 배치 GPU 추론 (8장씩)
    """
    list_cleanup_on_cancel = []
    try:
        import torch
        import numpy as np
        import cv2

        info = slide_manager.get(slide_id)
        if not info:
            _update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
            return

        # ── 캐시된 AI 결과 확인 (전체/ROI 무관 — 있으면 가져와서 표시) ──
        cache_path = _get_ai_cache_path(info.file_path, tissue_type)
        list_cleanup_on_cancel.append(cache_path)
        if cache_path.exists():
            try:
                _update_task(task_id, status="running", progress=10,
                             status_msg=f"Loading cached AI result: {cache_path.name}")
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                _update_task(task_id, status="completed", progress=100,
                             status_msg=f"Loaded cached result ({cached.get('total_cells', 0)} cells)",
                             result=cached)
                return
            except Exception as e:
                import traceback
                print(f"Cache load failed, running fresh inference: {e}\n{traceback.format_exc()}")

        _update_task(task_id, status="running", progress=1,
                     status_msg="Starting detection...")

        # ── 모델 로드 ──
        from ai.detection import non_max_suppression, CLASS_NAMES, CLASS_COLORS
        from ai.nets import nn as yolo_nn

        _update_task(task_id, progress=1, status_msg="Loading detection model...")

        model_path = Path(settings.MODEL_DIR) / "HnE_detection.pt"
        if not model_path.exists():
            _update_task(task_id, status="error", error=f"모델 파일 없음: {model_path}")
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        num_classes = 6
        model = yolo_nn.yolo_v11_m(num_classes).to(device)
        checkpoint = torch.load(str(model_path), map_location=device, weights_only=False)
        model.load_state_dict(checkpoint['model_state_dict'])
        model.eval()

        _update_task(task_id, progress=3, status_msg="Detection model loaded")

        # ── 설정 (기존 DetectionWorker와 동일) ──
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

        # ── 조직 마스크 (배경 스킵) ──
        _update_task(task_id, progress=4, status_msg="조직 마스크 생성 중...")
        thumb_mask = _create_tissue_mask(slide, icc_transform=info.icc_transform)
        _update_task(task_id, progress=5)

        # ── Pre-scan: 유효 패치 수집 ──
        valid_patch_list = []
        for pr in range(width // image_size - 1):
            for pc in range(height // image_size - 1):
                mx = (pr * image_size) // 64
                my = (pc * image_size) // 64
                if np.sum(thumb_mask[my:my + image_size // 64,
                                     mx:mx + image_size // 64]) == 0:
                    continue
                px, py = pr * image_size, pc * image_size
                # ROI 체크 (간단 바운딩박스)
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
        _update_task(task_id, progress=6, status_msg=f"유효 패치 {n_valid}개 발견")

        if n_valid == 0:
            _update_task(task_id, status="completed", progress=100, result={
                "total_cells": 0, "cells": [],
                "class_names": {str(k): v for k, v in CLASS_NAMES.items()},
                "class_colors": {str(k): v for k, v in CLASS_COLORS.items()},
            })
            return

        # ── numpy 청크 누적 (기존 방식: list-of-dicts 대신 numpy 배열) ──
        chunks_x, chunks_y, chunks_cls, chunks_conf = [], [], [], []
        detected_count = 0
        processed_valid = 0

        # ── I/O → 텐서 변환 함수 (스레드별 독립 OpenSlide) ──
        icc_tf = info.icc_transform
        def _read_patch_tensor(patch_x, patch_y):
            try:
                wait_if_viewer_busy()
                local_slide = _get_thread_slide(slide_id, slide_path)

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

        # ── 배치 GPU 추론 함수 (기존 _infer_batch와 동일) ──
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
                print(f"Batch inference error: {e}\n{traceback.format_exc()}")

            if not bx:
                ef = np.empty(0, dtype=np.float32)
                ei = np.empty(0, dtype=np.int32)
                return ef, ef.copy(), ei, ef.copy()
            return np.concatenate(bx), np.concatenate(by), np.concatenate(bcls), np.concatenate(bconf)

        # ══════════════════════════════════════
        # 파이프라인: I/O 프리페치 → 배치 GPU 추론
        # (기존 DetectionWorker._io_producer 로직 그대로)
        # ══════════════════════════════════════
        prefetch_q = queue.Queue(maxsize=PREFETCH_BATCHES)
        producer_done = threading.Event()

        def _io_producer():
            try:
                with ThreadPoolExecutor(max_workers=IO_WORKERS) as pool:
                    pending = []
                    for px, py in valid_patch_list:
                        if _is_cancel_requested(task_id):
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

                    # 남은 패치
                    if pending and not _is_cancel_requested(task_id):
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

        # ── GPU 추론 루프 ──
        while True:
            _check_cancel(task_id)
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
            pct = int(5 + (processed_valid / n_valid) * 45)  # 5~50%
            _update_task(task_id, progress=min(pct, 50),
                         status_msg=f"Detection: Patch {processed_valid}/{n_valid} | Cells: {detected_count}")

        producer_thread.join(timeout=10)

        # ── 결과 병합 ──
        if chunks_x:
            all_x = np.concatenate(chunks_x)
            all_y = np.concatenate(chunks_y)
            all_cls = np.concatenate(chunks_cls)
            all_conf = np.concatenate(chunks_conf)
        else:
            all_x = all_y = all_conf = np.empty(0, dtype=np.float32)
            all_cls = np.empty(0, dtype=np.int32)

        _check_cancel(task_id)
        _update_task(task_id, progress=50,
                     status_msg=f"Detection complete: {detected_count} cells")

        # ── Epithelial 재분류 (Breast/Stomach만) ──
        seg_data = None
        auto_classify = tissue_type in ("Breast", "Stomach")
        if auto_classify and len(all_cls) > 0:
            epithelial_count = int(np.sum(all_cls == 1))
            if epithelial_count > 0:
                _update_task(task_id, progress=52,
                             status_msg=f"Epithelial reclassification starting... ({epithelial_count} cells)")
                seg_data = _run_epithelial_classification(
                    task_id, slide, slide_path, info, all_x, all_y, all_cls,
                    tissue_type, roi_polygons, device,
                )
            else:
                _update_task(task_id, progress=98,
                             status_msg="No Epithelial cells found, skipping reclassification")
        elif not auto_classify:
            _update_task(task_id, progress=98,
                         status_msg="Tissue type 'Other' — skipping reclassification")

        n_cells = len(all_x)
        all_cells = [
            {
                "x": float(all_x[i]),
                "y": float(all_y[i]),
                "confidence": float(all_conf[i]),
                "class_id": int(all_cls[i]),
                "class_name": CLASS_NAMES.get(int(all_cls[i]), "Unknown"),
            }
            for i in range(n_cells)
        ]

        result = {
            "total_cells": n_cells,
            "cells": all_cells,
            "class_names": {str(k): v for k, v in CLASS_NAMES.items()},
            "class_colors": {str(k): v for k, v in CLASS_COLORS.items()},
            "seg_data": seg_data,
        }

        _check_cancel(task_id)
        # ── 전체 추론(폴리곤 없음)인 경우만 캐시 저장 ──
        if roi_polygons is None:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f)
                print(f"AI result cached: {cache_path}")
                from app import slide_store
                slide_store.mark_ai_result_threadsafe(info.file_path, "HE-Fit", tissue_type)
            except Exception as e:
                import traceback
                print(f"Cache save failed: {e}\n{traceback.format_exc()}")

        _update_task(task_id, status="completed", progress=100, result=result)

    except TaskCancelled:
        _cleanup_cache_paths(list_cleanup_on_cancel)
        _update_task(task_id, status="cancelled", progress=0,
                     status_msg="Cancelled by user", error=None)
        print(f"[cancel] _run_detection cancelled task={task_id}")
    except Exception as e:
        import traceback
        _update_task(task_id, status="error", error=f"{e}\n{traceback.format_exc()}")


def _create_tissue_mask(slide, icc_transform=None):
    """조직 마스크 생성 — H-DAB 분리 후 (Hem ∪ DAB ∪ 텍스처) − 확실한 배경.

    단일 Hematoxylin Otsu 만으로는 DAB 가 강하게 덮인 영역(H 가 억제됨)이나
    염색이 거의 없지만 구조가 있는 조직이 빠질 수 있음. 따라서:
      1) H-DAB color deconvolution (Ruifrok & Johnston 2001) → H / DAB 채널 분리
      2) 각 채널 Otsu → 염색 영역 검출
      3) 국소 표준편차(텍스처) Otsu → 무염색 조직 보완
      4) Union 후, 확실한 유리 배경(그레이 히스토그램 최고 피크의 95% 이상) 강제 제외

    icc_transform 이 주어지면 썸네일에 적용해 다른 AI 경로와 색상 일관성 유지.
    """
    import numpy as np
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

        # ── 텍스처(국소 std) — 무염색이지만 구조 있는 조직 보완 ──
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

        # ── 확실한 유리 배경 제거 (히스토그램 상단 피크의 95% 이상) ──
        hist = cv2.calcHist([np_gray], [0], None, [256], [0, 256]).flatten()
        bg_peak = int(np.argmax(hist[128:]) + 128)
        definite_bg = (np_gray >= int(bg_peak * 0.95))

        mask = (hem_mask > 0) | (dab_mask > 0) | (texture_mask > 0)
        mask[definite_bg] = False
        mask = (mask.astype(np.uint8)) * 255

        # 조각난 마스크를 넓게 CLOSE 해서 인접 조직 조각들을 하나로 묶음
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

        # ── 외곽 컨투어만 뽑아 솔리드로 채움 ──
        # → 내부 구멍(염색 옅어서 빠진 세포 간극)도 전부 tissue 로 포함
        # → 작은 면적 컨투어는 노이즈로 간주해 드랍
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        filled = np.zeros_like(mask)
        int_min_area = max(int(h * w * 0.0005), 50)  # 썸네일 면적의 0.05% 이상
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


def _run_epithelial_classification(task_id, slide, slide_path, info, all_x, all_y, all_cls,
                                    tissue_type, roi_polygons, device):
    """
    Epithelial 재분류: WSI Segmentation → Epithelial(1) → Tumor(6) / Benign(7)
    데스크톱 DetectionWorker._run_epithelial_classification과 동일 로직
    all_cls를 in-place로 수정한다.
    Returns: seg_data dict (seg_class_names, overlays as base64, thumbnail) or None
    """
    import numpy as np
    import torch

    try:
        from ai.epithelial_classifier import WSISegmentationModel

        # Segmentation 모델 경로
        if tissue_type == "Breast":
            seg_model_path = Path(settings.MODEL_DIR) / "HnE_BR_segmentation.pt"
        elif tissue_type == "Stomach":
            seg_model_path = Path(settings.MODEL_DIR) / "HnE_ST_segmentation.pt"
        else:
            return

        if not seg_model_path.exists():
            _update_task(task_id, status_msg=f"Segmentation model not found: {seg_model_path}")
            return

        _update_task(task_id, progress=52,
                     status_msg="Loading segmentation model...")

        seg_model = WSISegmentationModel(
            model_path=str(seg_model_path),
            model_mpp=1.0,
            output_mpp=4.0,
            device=device,
        )

        # ROI bounds 계산
        roi_bounds = None
        if roi_polygons:
            min_x = min(p[0] for poly in roi_polygons for p in poly)
            min_y = min(p[1] for poly in roi_polygons for p in poly)
            max_x = max(p[0] for poly in roi_polygons for p in poly)
            max_y = max(p[1] for poly in roi_polygons for p in poly)
            roi_bounds = (int(min_x), int(min_y), int(max_x), int(max_y))

        _update_task(task_id, progress=55,
                     status_msg="Running WSI Segmentation...")

        def progress_cb(pct):
            # 55~90% 구간
            _update_task(task_id, progress=55 + int(pct * 0.35),
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

        _update_task(task_id, progress=92,
                     status_msg="Reclassifying Epithelial cells...")

        # ── Epithelial 인덱스 및 mask 좌표 변환 ──
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

        # ── Connected component 클러스터링 ──
        from scipy import ndimage as ndi
        TUMOR_RATIO_THRESHOLD = 0.1
        epi_region = np.isin(prediction_mask, [2, 3]).astype(np.uint8)
        labeled_mask, num_components = ndi.label(epi_region, structure=np.ones((3, 3), dtype=np.int8))

        flat_label = labeled_mask.ravel()
        flat_mask = prediction_mask.ravel().astype(np.int32)
        n_bins = num_components + 1
        tumor_counts = np.bincount(flat_label, weights=(flat_mask == 3), minlength=n_bins)
        total_counts = np.bincount(flat_label, weights=np.isin(flat_mask, [2, 3]).astype(float), minlength=n_bins)
        with np.errstate(invalid='ignore', divide='ignore'):
            tumor_ratio = np.where(total_counts > 0, tumor_counts / total_counts, 0.0)
        comp_class_arr = np.where(tumor_ratio >= TUMOR_RATIO_THRESHOLD, 3, 2).astype(np.int32)
        comp_class_arr[0] = 0  # background

        lh, lw = labeled_mask.shape
        lvalid = (mxs >= 0) & (mxs < lw) & (mys >= 0) & (mys < lh)
        comp_ids = np.zeros(len(epi_indices), dtype=np.int32)
        comp_ids[lvalid] = labeled_mask[mys[lvalid], mxs[lvalid]]
        update_mask = comp_ids > 0
        seg_vals[update_mask] = comp_class_arr[comp_ids[update_mask]]

        # cls_arr in-place 업데이트: Benign(2)→7, Tumor(3)→6
        all_cls[epi_indices] = np.where(seg_vals == 2, 7, 6).astype(np.int32)

        _update_task(task_id, progress=98,
                     status_msg=f"Epithelial reclassification complete ({len(epi_indices)} cells)")

        # ── 썸네일 + 세그멘테이션 오버레이 생성 (프론트엔드 시각화용) ──
        seg_data = _build_seg_overlays(slide, prediction_mask, metadata,
                                       seg_model.class_names, roi_bounds,
                                       icc_transform=info.icc_transform)

        del seg_model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return seg_data

    except Exception as e:
        import traceback
        print(f"Epithelial reclassification failed: {e}\n{traceback.format_exc()}")
        _update_task(task_id, progress=98,
                     status_msg=f"Reclassification failed, using original results: {e}")
        return None


def _build_seg_overlays(slide, prediction_mask, metadata, class_names, roi_bounds, icc_transform=None):
    """
    세그멘테이션 확률맵(prob_map)을 썸네일 크기로 리사이즈하여 클래스별 오버레이 base64 생성.
    데스크톱의 _create_spatial_heatmap_tab과 동일: jet colormap + alpha=0.75 on probability maps.
    """
    import numpy as np
    import cv2
    import base64
    import io
    from PIL import Image

    try:
        # 썸네일 생성 (ROI 영역이면 해당 영역만)
        THUMB_SIZE = 800
        sw, sh = slide.dimensions
        if roi_bounds:
            x0, y0, x1, y1 = roi_bounds
        else:
            x0, y0, x1, y1 = 0, 0, sw, sh
        rw, rh = x1 - x0, y1 - y0

        # 썸네일 비율 유지
        if rw >= rh:
            tw = THUMB_SIZE
            th = max(1, int(THUMB_SIZE * rh / rw))
        else:
            th = THUMB_SIZE
            tw = max(1, int(THUMB_SIZE * rw / rh))

        # 썸네일 생성
        if roi_bounds:
            # ROI: 적절한 레벨에서 직접 read_region → 정확한 영역
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

        # 썸네일 → base64 JPEG
        _, thumb_buf = cv2.imencode('.jpeg', cv2.cvtColor(thumb_resized, cv2.COLOR_RGB2BGR),
                                     [cv2.IMWRITE_JPEG_QUALITY, 85])
        thumb_b64 = base64.b64encode(thumb_buf.tobytes()).decode('ascii')

        # ── 확률맵 기반 오버레이 (데스크톱과 동일) ──
        # metadata['prob_map'] = (num_classes, H, W) softmax probabilities
        # predict_wsi는 roi_bounds에 10% 버퍼를 추가하므로 mask/prob_map 영역 ≠ roi_bounds
        # → roi_bounds에 해당하는 부분만 crop 필요
        prob_map = metadata.get('prob_map')
        region_offset = metadata.get('region_offset', (0, 0))
        wsi_mpp = metadata.get('wsi_mpp', 0.25)
        output_mpp = metadata.get('output_mpp', 8.0)
        mpp_ratio = output_mpp / wsi_mpp  # mask 1px = WSI mpp_ratio px

        # mask/prob_map에서 roi_bounds에 해당하는 crop 인덱스 계산
        mask_h, mask_w = prediction_mask.shape
        if roi_bounds:
            # roi_bounds(WSI 좌표) → mask 좌표
            crop_mx0 = max(0, int((x0 - region_offset[0]) / mpp_ratio))
            crop_my0 = max(0, int((y0 - region_offset[1]) / mpp_ratio))
            crop_mx1 = min(mask_w, int((x1 - region_offset[0]) / mpp_ratio))
            crop_my1 = min(mask_h, int((y1 - region_offset[1]) / mpp_ratio))
        else:
            crop_mx0, crop_my0 = 0, 0
            crop_mx1, crop_my1 = mask_w, mask_h

        overlays = {}
        num_classes = len(class_names) if class_names else int(prediction_mask.max()) + 1

        for cls_id in range(1, num_classes):  # 0=Background 제외
            cls_name = class_names[cls_id] if class_names and cls_id < len(class_names) else f'Class_{cls_id}'

            if prob_map is not None and cls_id < prob_map.shape[0]:
                # roi 영역만 crop 후 썸네일 크기로 bilinear 리사이즈
                cropped = prob_map[cls_id][crop_my0:crop_my1, crop_mx0:crop_mx1].astype(np.float32)
                prob_resized = cv2.resize(cropped, (tw, th),
                                          interpolation=cv2.INTER_LINEAR)
            else:
                # fallback: argmax 마스크에서 crop → 이진 + blur
                cropped = prediction_mask[crop_my0:crop_my1, crop_mx0:crop_mx1].astype(np.uint8)
                mask_resized = cv2.resize(cropped, (tw, th),
                                           interpolation=cv2.INTER_NEAREST)
                prob_resized = cv2.GaussianBlur(
                    (mask_resized == cls_id).astype(np.float32), (7, 7), 2.0)

            # jet colormap 적용 (데스크톱: cmap='jet', alpha=0.75, vmin=0, vmax=1)
            cls_norm = (np.clip(prob_resized, 0, 1) * 255).astype(np.uint8)
            cls_jet = cv2.applyColorMap(cls_norm, cv2.COLORMAP_JET)
            # alpha: 확률값에 비례 (0.75 최대)
            alpha = (np.clip(prob_resized, 0, 1) * 0.75 * 255).astype(np.uint8)
            cls_rgba = np.dstack([cv2.cvtColor(cls_jet, cv2.COLOR_BGR2RGB), alpha])

            img = Image.fromarray(cls_rgba, 'RGBA')
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            overlays[cls_name] = base64.b64encode(buf.getvalue()).decode('ascii')

        return {
            'thumbnail': thumb_b64,
            'overlays': overlays,
            'class_names': class_names[1:] if class_names else [],  # Background 제외
            'width': tw,
            'height': th,
        }
    except Exception as e:
        import traceback
        print(f"Seg overlay generation failed: {e}\n{traceback.format_exc()}")
        return None


# ═══════════════════════════════════════════════════════════════════
# PD-Score (PD-L1) — Stomach: CPS / Lung: TPS
# ═══════════════════════════════════════════════════════════════════

PD_SCORE_CONFIG = {
    "Stomach": {
        "model_file": "PDL1_ST_CPS_detection.pt",
        "num_classes": 7,
        "class_names": {
            0: "Negative Epithelial",
            1: "Negative Lymphocyte",
            2: "Negative Macrophage",
            3: "Positive Epithelial",
            4: "Positive Lymphocyte",
            5: "Positive Macrophage",
            6: "Other",
        },
        "class_colors": {
            0: "#1e8449",
            1: "#27ae60",
            2: "#16a085",
            3: "#922b21",
            4: "#e74c3c",
            5: "#ec7063",
            6: "#95a5a6",
        },
        "score_type": "CPS",
        "exclude_classes": [6],
    },
    "Lung": {
        "model_file": "PDL1_TPS_detection.pt",
        "num_classes": 3,
        "class_names": {
            0: "PD-L1 Negative Tumor",
            1: "PD-L1 Positive Tumor",
            2: "Non-Tumor Cell",
        },
        "class_colors": {
            0: "#3498db",
            1: "#e74c3c",
            2: "#95a5a6",
        },
        "score_type": "TPS",
        "exclude_classes": [],
    },
}


def _get_pd_score_cache_path(slide_path: str, tissue_type: str) -> Path:
    """PD-Score 결과 캐시: ai_results/PD-Score/{slide_stem}_PD-Score_{tissue_type}.json"""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "PD-Score"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return cache_dir / f"{p.stem}_PD-Score_{tissue_type}.json"


def _compute_pd_score(all_cls, tissue_type: str) -> dict:
    """
    CPS (Stomach): (positive tumor + positive immune) / viable tumor * 100, capped at 100
                   - positive tumor = cls 3 (positive Epithelial)
                   - positive immune = cls 4 + cls 5 (positive lymphocyte/macrophage)
                   - viable tumor = cls 0 + cls 3 (all epithelial)
    TPS  (Lung):   positive tumor / (positive + negative tumor) * 100
                   - positive tumor = cls 1
                   - negative tumor = cls 0
    """
    import numpy as np

    score_type = PD_SCORE_CONFIG[tissue_type]["score_type"]
    int_counts = {int(c): int((all_cls == c).sum()) for c in range(PD_SCORE_CONFIG[tissue_type]["num_classes"])}

    if score_type == "CPS":
        int_pos_tumor = int_counts.get(3, 0)
        int_pos_immune = int_counts.get(4, 0) + int_counts.get(5, 0)
        int_viable_tumor = int_counts.get(0, 0) + int_counts.get(3, 0)
        if int_viable_tumor == 0:
            float_score = 0.0
        else:
            float_score = min(100.0, (int_pos_tumor + int_pos_immune) / int_viable_tumor * 100.0)
        return {
            "score_type": "CPS",
            "score": round(float_score, 2),
            "positive_tumor": int_pos_tumor,
            "positive_immune": int_pos_immune,
            "viable_tumor": int_viable_tumor,
            "class_counts": int_counts,
        }
    else:  # TPS
        int_pos_tumor = int_counts.get(1, 0)
        int_neg_tumor = int_counts.get(0, 0)
        int_total_tumor = int_pos_tumor + int_neg_tumor
        if int_total_tumor == 0:
            float_score = 0.0
        else:
            float_score = int_pos_tumor / int_total_tumor * 100.0
        return {
            "score_type": "TPS",
            "score": round(float_score, 2),
            "positive_tumor": int_pos_tumor,
            "negative_tumor": int_neg_tumor,
            "total_tumor": int_total_tumor,
            "class_counts": int_counts,
        }


def _run_marker_detection_pipeline(
    task_id, slide_id, roi_polygons,
    dict_config, cache_path,
    score_fn, score_key,
    extra_fields, log_label,
    str_variant: str = "",
    float_score_conf_threshold: float = 0.1,
):
    """
    YOLOv11m 기반 marker detection 공용 파이프라인.
    PD-Score / Precise-IHC 가 공유.
    """
    list_cleanup_on_cancel = [cache_path]
    try:
        import torch
        import numpy as np
        import cv2

        info = slide_manager.get(slide_id)
        if not info:
            _update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
            return

        dict_class_names = dict_config["class_names"]
        dict_class_colors = dict_config["class_colors"]
        int_num_classes = dict_config["num_classes"]
        list_exclude = dict_config.get("exclude_classes") or []

        # ── 캐시 확인 ──
        if cache_path.exists():
            try:
                _update_task(task_id, status="running", progress=10,
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

                _update_task(task_id, status="completed", progress=100,
                             status_msg=f"Loaded cached result ({cached.get('total_cells', 0)} cells)",
                             result=cached)
                return
            except Exception as e:
                import traceback
                print(f"{log_label} cache load failed: {e}\n{traceback.format_exc()}")

        _update_task(task_id, status="running", progress=1,
                     status_msg=f"Starting {log_label} detection...")

        # ── 모델 로드 ──
        from ai.detection import non_max_suppression
        from ai.nets import nn as yolo_nn

        model_path = Path(settings.MODEL_DIR) / dict_config["model_file"]
        if not model_path.exists():
            _update_task(task_id, status="error", error=f"모델 파일 없음: {model_path}")
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = yolo_nn.yolo_v11_m(int_num_classes).to(device)
        checkpoint = torch.load(str(model_path), map_location=device, weights_only=False)

        # PDL1 체크포인트는 DFL 채널수가 4 (기본 16 대신). head 를 재구성하여 shape 맞춤.
        state_dict = checkpoint['model_state_dict']
        dfl_weight = state_dict.get('head.dfl.conv.weight')
        if dfl_weight is not None and dfl_weight.shape[1] != model.head.ch:
            int_ch_ckpt = int(dfl_weight.shape[1])
            _update_task(task_id, status_msg=f"Rebuilding head with DFL ch={int_ch_ckpt}")
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

        _update_task(task_id, progress=3, status_msg=f"{log_label} model loaded")

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
        _update_task(task_id, progress=4, status_msg="조직 마스크 생성 중...")
        thumb_mask = _create_tissue_mask(slide, icc_transform=info.icc_transform)
        _update_task(task_id, progress=5)

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
        _update_task(task_id, progress=6, status_msg=f"유효 패치 {n_valid}개 발견")

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
            _update_task(task_id, status="completed", progress=100, result=empty_result)
            return

        chunks_x, chunks_y, chunks_cls, chunks_conf = [], [], [], []
        detected_count = 0
        processed_valid = 0

        icc_tf = info.icc_transform
        def _read_patch_tensor(patch_x, patch_y):
            try:
                wait_if_viewer_busy()
                local_slide = _get_thread_slide(slide_id, slide_path)

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
                        if _is_cancel_requested(task_id):
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

                    if pending and not _is_cancel_requested(task_id):
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
            _check_cancel(task_id)
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
            _update_task(task_id, progress=min(pct, 95),
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
        _update_task(task_id, progress=97,
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

        # Score 는 프론트엔드 기본 confidence 필터(0.1)와 동일한 임계값으로 계산.
        # PD-Score/Precise-IHC 모델은 표시 시 conf < 0.1 셀을 숨기므로,
        # 초기 노출되는 CPS/TPS/HER2 점수도 같은 필터를 거친 cells 로부터 구해야 일관적이다.
        # (cells 리스트 전체는 그대로 저장 — 사용자가 임계값을 낮추면 셀은 더 표시됨)
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

        _check_cancel(task_id)
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

        _update_task(task_id, status="completed", progress=100, result=result)

    except TaskCancelled:
        _cleanup_cache_paths(list_cleanup_on_cancel)
        _update_task(task_id, status="cancelled", progress=0,
                     status_msg="Cancelled by user", error=None)
        print(f"[cancel] {log_label} cancelled task={task_id}")
    except Exception as e:
        import traceback
        _update_task(task_id, status="error", error=f"{e}\n{traceback.format_exc()}")


def _run_pd_score(task_id, slide_id, roi_polygons, tissue_type):
    """PD-Score 파이프라인 wrapper (공용 marker pipeline 호출)."""
    dict_config = PD_SCORE_CONFIG[tissue_type]
    info = slide_manager.get(slide_id)
    if not info:
        _update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
        return
    cache_path = _get_pd_score_cache_path(info.file_path, tissue_type)
    _run_marker_detection_pipeline(
        task_id=task_id,
        slide_id=slide_id,
        roi_polygons=roi_polygons,
        dict_config=dict_config,
        cache_path=cache_path,
        score_fn=lambda all_cls: _compute_pd_score(all_cls, tissue_type),
        score_key="pd_score",
        extra_fields={"tissue_type": tissue_type},
        log_label="PD-Score",
        str_variant=tissue_type,
    )


# ═══════════════════════════════════════════════════════════════════
# Precise-IHC — HER2 / ER-PR / KI-67 (현재 HER2 만 활성화)
# ═══════════════════════════════════════════════════════════════════

PRECISE_IHC_CONFIG = {
    "HER2": {
        "model_file": "Precise_IHC_HER2_detection.pt",
        "num_classes": 5,
        "class_names": {
            0: "HER2 0+",
            1: "HER2 1+",
            2: "HER2 2+",
            3: "HER2 3+",
            4: "Other",
        },
        # class0 (0+) 초록 → class3 (3+) 새빨강. class 숫자 ↑ → red ↑
        "class_colors": {
            0: "#27ae60",  # green (0+)
            1: "#f1c40f",  # yellow (1+)
            2: "#e67e22",  # orange (2+)
            3: "#c0392b",  # deep red (3+)
            4: "#95a5a6",  # other (hidden)
        },
        "score_type": "HER2",
        "exclude_classes": [4],
    },
    # ER/PR: HER2 와 동일한 5-class 모델 구조 (intensity 0+~3+ + Other).
    # ER 과 PR 은 동일 .pt 를 공유하고 추론 결과도 동일하므로 단일 marker("ER_PR") 로 통합.
    "ER_PR": {
        "model_file": "Precise_IHC_ER_PR_detection.pt",
        "num_classes": 5,
        "class_names": {
            0: "ER/PR 0+",
            1: "ER/PR 1+",
            2: "ER/PR 2+",
            3: "ER/PR 3+",
            4: "Other",
        },
        "class_colors": {
            0: "#27ae60",
            1: "#f1c40f",
            2: "#e67e22",
            3: "#c0392b",
            4: "#95a5a6",
        },
        "score_type": "Allred",
        "exclude_classes": [4],
    },
}


def _get_precise_ihc_cache_path(slide_path: str, marker: str) -> Path:
    """Precise-IHC 결과 캐시: ai_results/Precise-IHC/{slide_stem}_Precise-IHC_{marker}.json"""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Precise-IHC"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return cache_dir / f"{p.stem}_Precise-IHC_{marker}.json"


def _compute_her2_score(all_cls) -> dict:
    """
    HER2 score:
      - 클래스 0~3 은 intensity 0+/1+/2+/3+
      - 가중 평균 = Σ(i * n_i) / Σ(n_i)  (i = 0..3)
      - dominant_class = 가장 많은 intensity
    """
    import numpy as np
    int_counts = {int(c): int((all_cls == c).sum()) for c in range(4)}
    int_total = sum(int_counts.values())
    if int_total == 0:
        return {
            "score_type": "HER2",
            "score": 0.0,
            "dominant_class": 0,
            "total_tumor": 0,
            "class_counts": int_counts,
        }
    float_weighted = sum(i * int_counts[i] for i in range(4)) / int_total
    int_dominant = max(int_counts, key=lambda k: int_counts[k])
    return {
        "score_type": "HER2",
        "score": round(float_weighted, 3),
        "dominant_class": int_dominant,
        "total_tumor": int_total,
        "class_counts": int_counts,
    }


def _compute_allred_score(all_cls) -> dict:
    """
    Allred score (ER/PR):
      - intensity 클래스 0~3 (none / weak / intermediate / strong)
      - Proportion Score (PS): 양성 비율 (positive / total tumor)
          0=0%, 1=<1%, 2=1-10%, 3=10-33%, 4=33-66%, 5=>66%
      - Intensity Score (IS): 양성 세포 평균 강도 → bin 0/1/2/3
          (avg < 0.5: 0, 0.5–1.5: 1, 1.5–2.5: 2, ≥2.5: 3)
      - Total Score (TS) = PS + IS (0~8). 3 이상 → Positive.
    """
    import numpy as np
    int_counts = {int(c): int((all_cls == c).sum()) for c in range(4)}
    n0, n1, n2, n3 = int_counts[0], int_counts[1], int_counts[2], int_counts[3]
    int_total = n0 + n1 + n2 + n3
    int_pos = n1 + n2 + n3

    if int_total == 0:
        return {
            "score_type": "Allred",
            "proportion_score": 0,
            "intensity_score": 0,
            "total_score": 0,
            "positive_pct": 0.0,
            "avg_intensity": 0.0,
            "interpretation": "Negative",
            "total_tumor": 0,
            "class_counts": int_counts,
        }

    float_pos_pct = int_pos / int_total * 100.0
    if int_pos == 0:
        int_ps = 0
    elif float_pos_pct < 1.0:
        int_ps = 1
    elif float_pos_pct < 10.0:
        int_ps = 2
    elif float_pos_pct < 33.0:
        int_ps = 3
    elif float_pos_pct < 66.0:
        int_ps = 4
    else:
        int_ps = 5

    if int_pos == 0:
        float_avg = 0.0
        int_is = 0
    else:
        float_avg = (1 * n1 + 2 * n2 + 3 * n3) / int_pos
        if float_avg < 0.5:
            int_is = 0
        elif float_avg < 1.5:
            int_is = 1
        elif float_avg < 2.5:
            int_is = 2
        else:
            int_is = 3

    int_ts = int_ps + int_is
    str_interp = "Positive" if int_ts >= 3 else "Negative"

    return {
        "score_type": "Allred",
        "proportion_score": int_ps,
        "intensity_score": int_is,
        "total_score": int_ts,
        "positive_pct": round(float_pos_pct, 2),
        "avg_intensity": round(float_avg, 3),
        "interpretation": str_interp,
        "total_tumor": int_total,
        "class_counts": int_counts,
    }


def _run_precise_ihc(task_id, slide_id, roi_polygons, marker: str):
    """Precise-IHC 파이프라인 wrapper — HER2 / ER_PR 지원."""
    if marker not in PRECISE_IHC_CONFIG:
        _update_task(task_id, status="error", error=f"지원하지 않는 marker: {marker}")
        return
    dict_config = PRECISE_IHC_CONFIG[marker]
    info = slide_manager.get(slide_id)
    if not info:
        _update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
        return
    cache_path = _get_precise_ihc_cache_path(info.file_path, marker)

    if marker == "HER2":
        score_fn = _compute_her2_score
        score_key = "her2_score"
    elif marker == "ER_PR":
        score_fn = _compute_allred_score
        score_key = "allred_score"
    else:
        score_fn = lambda all_cls: {"score_type": marker, "score": 0.0}
        score_key = f"{marker.lower()}_score"

    _run_marker_detection_pipeline(
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
    )


# ═══ API 엔드포인트 ═══

@router.post("/detect")
async def start_detection(
    request: Request,
    slide_id: str = Form(...),
    roi_polygons: Optional[str] = Form(None),
    tissue_type: str = Form("Stomach"),
    dict_user: dict = Depends(get_current_user),
):
    """검출 작업 시작 (비동기)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    task_id = uuid.uuid4().hex[:12]
    polygons = json.loads(roi_polygons) if roi_polygons else None
    str_filename = Path(info.file_path).name

    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued", "progress": 0,
            "result": None, "error": None, "status_msg": "",
            "slide_filename": str_filename,
            "model": "HE-Fit", "variant": tissue_type,
        }

    t = threading.Thread(
        target=_run_detection,
        args=(task_id, slide_id, polygons, tissue_type),
        daemon=True,
    )
    t.start()

    await _log_ai_analyze(request, dict_user, "HE-Fit", tissue_type, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.post("/pd-score")
async def start_pd_score(
    request: Request,
    slide_id: str = Form(...),
    roi_polygons: Optional[str] = Form(None),
    tissue_type: str = Form("Stomach"),
    dict_user: dict = Depends(get_current_user),
):
    """PD-Score 추론 시작 (Stomach → CPS, Lung → TPS)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    if tissue_type not in PD_SCORE_CONFIG:
        raise HTTPException(400, f"지원하지 않는 조직 타입: {tissue_type}")

    task_id = uuid.uuid4().hex[:12]
    polygons = json.loads(roi_polygons) if roi_polygons else None
    str_filename = Path(info.file_path).name

    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued", "progress": 0,
            "result": None, "error": None, "status_msg": "",
            "slide_filename": str_filename,
            "model": "PD-Score", "variant": tissue_type,
        }

    t = threading.Thread(
        target=_run_pd_score,
        args=(task_id, slide_id, polygons, tissue_type),
        daemon=True,
    )
    t.start()

    await _log_ai_analyze(request, dict_user, "PD-Score", tissue_type, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.post("/precise-ihc")
async def start_precise_ihc(
    request: Request,
    slide_id: str = Form(...),
    roi_polygons: Optional[str] = Form(None),
    marker: str = Form("HER2"),
    dict_user: dict = Depends(get_current_user),
):
    """Precise-IHC 추론 시작 (marker: HER2 / ER_PR)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    if marker not in PRECISE_IHC_CONFIG:
        raise HTTPException(400, f"지원하지 않는 marker: {marker}")

    task_id = uuid.uuid4().hex[:12]
    polygons = json.loads(roi_polygons) if roi_polygons else None
    str_filename = Path(info.file_path).name

    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued", "progress": 0,
            "result": None, "error": None, "status_msg": "",
            "slide_filename": str_filename,
            "model": "Precise-IHC", "variant": marker,
        }

    t = threading.Thread(
        target=_run_precise_ihc,
        args=(task_id, slide_id, polygons, marker),
        daemon=True,
    )
    t.start()

    await _log_ai_analyze(request, dict_user, "Precise-IHC", marker, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.get("/active-tasks")
async def get_active_tasks():
    """현재 queued/running 상태인 AI 작업을 슬라이드 파일명 기준으로 그룹화하여 반환.

    응답 형식:
        {"active": {filename: [{"model": ..., "variant": ..., "status": ...}, ...], ...}}
    """
    dict_active: dict[str, list] = {}
    with _tasks_lock:
        for _, dict_task in _tasks.items():
            if dict_task.get("status") not in ("queued", "running"):
                continue
            str_fn = dict_task.get("slide_filename")
            if not str_fn:
                continue
            dict_active.setdefault(str_fn, []).append({
                "model": dict_task.get("model") or "",
                "variant": dict_task.get("variant") or "",
                "status": dict_task.get("status"),
            })
    return {"active": dict_active}


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """AI 작업 상태 조회"""
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "작업을 찾을 수 없습니다")

    response = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "status_msg": task.get("status_msg", ""),
    }
    if task["status"] == "completed":
        response["result"] = task["result"]
    elif task["status"] == "error":
        response["error"] = task["error"]
    return response


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """실행 중인 AI 작업 취소 요청.

    - queued/running 이면 cancel_requested 플래그 세팅 → 워커가 다음 체크포인트에서 중단
    - 워커는 부분 저장된 캐시(JSON/PNG/타일 폴더)를 삭제해 다음 실행 시 충돌 방지
    """
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(404, "작업을 찾을 수 없습니다")
        str_status = task.get("status")
        if str_status in ("completed", "error", "cancelled"):
            return {"task_id": task_id, "status": str_status, "msg": "already finished"}
        task["cancel_requested"] = True
        task["status_msg"] = "Cancelling..."
    print(f"[cancel] requested for task {task_id}")
    return {"task_id": task_id, "status": "cancelling"}


@router.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    """AI 작업 결과 조회"""
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    if task["status"] != "completed":
        raise HTTPException(400, f"작업 미완료 (status: {task['status']})")
    return task["result"]


@router.post("/save-result")
async def save_detection_result(
    slide_id: str = Form(...),
    tissue_type: str = Form("Stomach"),
    result: str = Form(...),
):
    """
    검출 결과를 서버 내부 AI 결과 폴더에 저장 (다운로드 X).
    파일: AI_RESULTS_DIR/{slide_stem}_HE-Fit_{tissue_type}.json
    """
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    try:
        result_obj = json.loads(result)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    cache_path = _get_ai_cache_path(info.file_path, tissue_type)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(result_obj, f)
    except Exception as e:
        raise HTTPException(500, f"Save failed: {e}")

    # DB 에 AI 결과 플래그 기록 (async 컨텍스트 — 직접 await)
    from app import slide_store
    from pathlib import Path as _P
    try:
        p = _P(info.file_path).resolve()
        upload_dir = _P(settings.UPLOAD_DIR).resolve()
        str_rel_path = str(p.parent.relative_to(upload_dir)).replace("\\", "/")
        if str_rel_path in (".", ""):
            str_rel_path = ""
        await slide_store.mark_ai_result(str_rel_path, p.name, "HE-Fit", tissue_type)
    except Exception as e:
        print(f"[ai] mark_ai_result (save-result) failed: {e}")

    return {
        "saved": True,
        "path": str(cache_path),
        "filename": cache_path.name,
        "total_cells": result_obj.get("total_cells", 0),
    }


# ═══════════════════════════════════════════════════════════════════
# Virtual Stain (VS-IHC) — IHC → H&E
# ═══════════════════════════════════════════════════════════════════

VS_MODEL_FILES = {
    "ihc_membrane": "IHC_HnE_virtual_stain_membrane.pth",
    "ihc_nucleus": "IHC_HnE_virtual_stain_nucleus.pth",
}


def _get_vs_cache_paths(slide_path: str, stain_type: str, target_mpp: float = 2.0):
    """
    Virtual stain 결과 캐시: ai_results/VS-IHC/{slide_stem}_VS-IHC_{stain}_mpp{p}.{png|json}
    타일 피라미드는 sibling 폴더: ..._tile/{level}/{tx}_{ty}.jpeg
    레거시 (ai_results 루트) 경로가 있으면 새 위치로 자동 이동.
    """
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "VS-IHC"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    mpp_str = f"{target_mpp:g}".replace(".", "p")
    base_name = f"{p.stem}_VS-IHC_{stain_type}_mpp{mpp_str}"
    new_png = (cache_dir / base_name).with_suffix(".png")
    new_meta = (cache_dir / base_name).with_suffix(".json")

    legacy_dir = Path(settings.AI_RESULTS_DIR)
    legacy_png = (legacy_dir / base_name).with_suffix(".png")
    legacy_meta = (legacy_dir / base_name).with_suffix(".json")
    legacy_tile = legacy_dir / f"{base_name}_tile"

    for src, dst in ((legacy_png, new_png), (legacy_meta, new_meta)):
        if src.exists() and not dst.exists():
            try:
                src.replace(dst)
            except Exception as e:
                print(f"[ai] VS legacy migration failed ({src.name}): {e}")
    if legacy_tile.exists() and not (cache_dir / f"{base_name}_tile").exists():
        try:
            legacy_tile.replace(cache_dir / f"{base_name}_tile")
        except Exception as e:
            print(f"[ai] VS legacy tile dir migration failed: {e}")
    return new_png, new_meta


def _get_vs_tile_dir(slide_path: str, stain_type: str, target_mpp: float = 2.0) -> Path:
    """VS 타일 피라미드 폴더: {png_parent}/{png_stem}_tile/"""
    png_path, _ = _get_vs_cache_paths(slide_path, stain_type, target_mpp)
    return png_path.parent / f"{png_path.stem}_tile"


def _generate_vs_tiles(output_canvas, tile_dir: Path,
                       tile_size: int = 512, n_levels: int = 4,
                       quality: int = 88) -> list[dict]:
    """
    output_canvas (uint8 H×W×3 또는 H×W×4) → 4단계 피라미드 JPEG 타일 생성.
    레벨 0 = 원본 해상도, 각 레벨은 /2 다운샘플.
    완전히 흰 타일은 스킵 (서빙 시 404 → 프론트에서 무시).
    반환: [{"level":0,"width":W,"height":H,"nx":..,"ny":..,"tile_count":..}, ...]
    """
    import numpy as np
    from PIL import Image

    if tile_dir.exists():
        # 기존 타일 제거 (재생성 시 stale 제거)
        try:
            import shutil
            shutil.rmtree(tile_dir)
        except Exception:
            pass
    tile_dir.mkdir(parents=True, exist_ok=True)

    # RGBA → RGB (alpha=0 영역은 흰색 배경으로 합성해 JPEG 저장)
    if output_canvas.ndim == 3 and output_canvas.shape[2] == 4:
        rgb = output_canvas[:, :, :3].copy()
        a = output_canvas[:, :, 3]
        mask = a < 255
        if mask.any():
            rgb[mask] = 255
        pil = Image.fromarray(rgb, 'RGB')
    else:
        pil = Image.fromarray(output_canvas, 'RGB')

    levels_meta: list[dict] = []
    current = pil
    for lv in range(n_levels):
        w, h = current.size
        nx = (w + tile_size - 1) // tile_size
        ny = (h + tile_size - 1) // tile_size
        level_dir = tile_dir / str(lv)
        level_dir.mkdir(parents=True, exist_ok=True)

        arr = np.asarray(current)
        count = 0
        for ty in range(ny):
            for tx in range(nx):
                left = tx * tile_size
                upper = ty * tile_size
                right = min(left + tile_size, w)
                lower = min(upper + tile_size, h)
                patch = arr[upper:lower, left:right]
                # 거의 전부 흰색이면 스킵 (디스크 절약)
                if patch.size == 0:
                    continue
                if patch.min() >= 248:
                    continue
                tile_img = Image.fromarray(patch, 'RGB')
                tile_img.save(level_dir / f"{tx}_{ty}.jpeg", "JPEG",
                              quality=quality, optimize=False)
                count += 1

        levels_meta.append({
            "level": lv, "width": int(w), "height": int(h),
            "nx": int(nx), "ny": int(ny), "tile_count": int(count),
        })

        if lv < n_levels - 1:
            new_w = max(1, w // 2)
            new_h = max(1, h // 2)
            current = current.resize((new_w, new_h), Image.BILINEAR)

    return levels_meta


def _run_virtual_stain(task_id: str, slide_id: str,
                       roi_polygons, stain_type: str,
                       target_mpp: float = 2.0):
    """
    Virtual staining 백그라운드 작업.
    desktop ai/virtual_stain.py 의 VirtualStainWorker.run() 로직을 그대로 옮김.
    Qt 시그널 대신 _update_task() 사용.
    """
    list_cleanup_on_cancel = []
    try:
        import torch
        import numpy as np
        from PIL import Image
        import openslide

        from ai.virtual_stain import (
            Generator, _make_blend_weight, _read_patch, VirtualStainWorker
        )

        # Pillow의 decompression-bomb 가드 해제 (VS composite 가 수억 px 일 수 있음)
        Image.MAX_IMAGE_PIXELS = None

        info = slide_manager.get(slide_id)
        if not info:
            _update_task(task_id, status="error", error="슬라이드를 찾을 수 없습니다")
            return

        # ── ROI 폴리곤 보관 (표시 클립용; 추론은 항상 전체로 수행) ──
        # 추론/저장은 ROI 무시하고 전체로 진행해 캐시를 만든다.
        # 단, 사용자가 ROI를 지정한 경우 그 폴리곤은 결과에 그대로 담아 프론트에서
        # 오버레이를 ROI 영역으로만 클립해 보여주도록 한다.
        display_roi_polygons = roi_polygons
        roi_polygons = None  # 전체 추론 강제

        # ── 캐시 확인 ──
        png_path, meta_path = _get_vs_cache_paths(info.file_path, stain_type, target_mpp)
        # 캐시 hit 경로에서는 cleanup 등록 금지 (기존 멀쩡한 캐시를 지울 수 있음).
        # 새 추론이 실제로 파일을 쓰기 직전 아래에서만 등록한다.
        if png_path.exists() and meta_path.exists():
            try:
                _update_task(task_id, status="running", progress=10,
                             status_msg=f"Loading cached virtual stain: {png_path.name}")
                with open(meta_path, 'r', encoding='utf-8') as f:
                    cached_meta = json.load(f)

                # 레거시 캐시: 타일 피라미드가 없으면 PNG에서 1회 업그레이드 생성
                tile_dir = _get_vs_tile_dir(info.file_path, stain_type, target_mpp)
                if (not cached_meta.get("levels")) or (not tile_dir.exists()):
                    try:
                        _update_task(task_id, progress=30,
                                     status_msg="Upgrading legacy cache → tile pyramid...")
                        legacy_png = Image.open(str(png_path))
                        if legacy_png.mode == 'RGBA':
                            bg = Image.new('RGB', legacy_png.size, (255, 255, 255))
                            bg.paste(legacy_png, mask=legacy_png.split()[3])
                            legacy_arr = np.asarray(bg)
                        else:
                            legacy_arr = np.asarray(legacy_png.convert('RGB'))
                        tile_size_px = int(cached_meta.get("tile_size", 512))
                        levels_meta = _generate_vs_tiles(
                            legacy_arr, tile_dir,
                            tile_size=tile_size_px, n_levels=4,
                        )
                        cached_meta['tile_size'] = tile_size_px
                        cached_meta['levels'] = levels_meta
                        with open(meta_path, 'w', encoding='utf-8') as f:
                            json.dump(cached_meta, f)
                    except Exception as e:
                        import traceback
                        print(f"VS legacy tile upgrade failed: {e}\n{traceback.format_exc()}")

                cached_meta['image_filename'] = png_path.name
                cached_meta['cached'] = True
                if display_roi_polygons is not None:
                    cached_meta['roi_polygons'] = display_roi_polygons
                _update_task(task_id, status="completed", progress=100,
                             status_msg="Loaded cached virtual stain",
                             result=cached_meta)
                return
            except Exception as e:
                print(f"VS cache load failed, running fresh: {e}")

        # ── 모델 경로 확인 ──
        model_filename = VS_MODEL_FILES.get(stain_type)
        if not model_filename:
            _update_task(task_id, status="error",
                         error=f"Unknown stain type: {stain_type}")
            return
        model_path = Path(settings.MODEL_DIR) / model_filename
        if not model_path.exists():
            _update_task(task_id, status="error",
                         error=f"Virtual stain model not found: {model_path}")
            return

        _update_task(task_id, status="running", progress=1,
                     status_msg="Loading virtual stain model...")

        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        use_fp16 = (device.type == 'cuda')

        generator = Generator(3, 3).to(device)
        generator.load_state_dict(torch.load(str(model_path), map_location=device))
        generator.eval()
        if use_fp16:
            generator = generator.half()

        _update_task(task_id, progress=3, status_msg="Opening slide...")

        slide_path = info.file_path
        slide = openslide.OpenSlide(slide_path)

        # target_mpp is provided as parameter
        patch_size = 512
        batch_size = 4

        native_mpp = float(slide.properties.get('openslide.mpp-x', 0.25))
        downsample_factor = target_mpp / native_mpp
        ps = patch_size
        overlap = ps // 4
        stride = ps - overlap
        read_size = int(ps * downsample_factor)
        read_stride = int(stride * downsample_factor)

        best_level = slide.get_best_level_for_downsample(downsample_factor)
        level_ds = slide.level_downsamples[best_level]
        level_read = int(read_size / level_ds)

        W, H = slide.dimensions

        # ROI bounds 계산 (폴리곤 → bounding box)
        roi_bounds = None
        if roi_polygons:
            xs = [p[0] for poly in roi_polygons for p in poly]
            ys = [p[1] for poly in roi_polygons for p in poly]
            roi_bounds = (
                max(0, int(min(xs))), max(0, int(min(ys))),
                min(W, int(max(xs))), min(H, int(max(ys))),
            )

        if roi_bounds:
            x_min, y_min, x_max, y_max = roi_bounds
        else:
            x_min, y_min, x_max, y_max = 0, 0, W, H

        # ROI가 한 패치보다 작으면 read_size로 확장 (슬라이드 경계 안에서 클램프)
        if x_max - x_min < read_size:
            cx = (x_min + x_max) // 2
            x_min = max(0, cx - read_size // 2)
            x_max = min(W, x_min + read_size)
            x_min = max(0, x_max - read_size)
        if y_max - y_min < read_size:
            cy = (y_min + y_max) // 2
            y_min = max(0, cy - read_size // 2)
            y_max = min(H, y_min + read_size)
            y_min = max(0, y_max - read_size)

        if W < read_size or H < read_size:
            _update_task(task_id, status="error",
                         error=f"Slide too small for target_mpp={target_mpp} "
                               f"(needs >= {read_size}px at level-0, slide is {W}x{H}).")
            slide.close()
            return

        pos_x = list(range(x_min, x_max - read_size + 1, read_stride))
        pos_y = list(range(y_min, y_max - read_size + 1, read_stride))
        if not pos_x:
            pos_x = [x_min]
        if not pos_y:
            pos_y = [y_min]
        if pos_x[-1] + read_size < x_max:
            pos_x.append(max(pos_x[-1] + read_stride, x_max - read_size))
        if pos_y[-1] + read_size < y_max:
            pos_y.append(max(pos_y[-1] + read_stride, y_max - read_size))

        n_px, n_py = len(pos_x), len(pos_y)
        out_w = (n_px - 1) * stride + ps
        out_h = (n_py - 1) * stride + ps
        canvas_l0_w = pos_x[-1] + read_size - x_min
        canvas_l0_h = pos_y[-1] + read_size - y_min

        _update_task(task_id, progress=5, status_msg="Creating tissue mask...")

        # tissue grid 빌드는 worker의 메서드를 직접 호출 (인스턴스 불필요한 staticmethod 형태가 아니라
        # 인스턴스 메서드여서 래핑 필요) — 가장 단순한 방법: dummy worker 인스턴스 생성
        dummy_worker = VirtualStainWorker(
            image_path=slide_path,
            model_path=str(model_path),
            stain_type=stain_type,
            target_mpp=target_mpp,
            patch_size=patch_size,
            batch_size=batch_size,
            roi_bounds=roi_bounds,
            roi_polygons=roi_polygons,
        )
        tissue_grid, tissue_pixel_mask = dummy_worker._build_tissue_grid(
            slide, x_min, y_min, canvas_l0_w, canvas_l0_h,
            n_px, n_py, stride, ps, out_w, out_h,
        )
        tissue_total = int(tissue_grid.sum())
        _update_task(task_id, progress=8,
                     status_msg=f"Grid {n_px}x{n_py}: {tissue_total} tissue patches")

        # ── 패치 리스트 ──
        all_patches = []
        for yi in range(n_py):
            for xi in range(n_px):
                x0 = pos_x[xi]
                y0 = pos_y[yi]
                out_of_bounds = (x0 + read_size > W) or (y0 + read_size > H)
                is_tissue = bool(tissue_grid[yi, xi]) and not out_of_bounds
                all_patches.append((xi, yi, x0, y0,
                                    xi * stride, yi * stride, is_tissue))

        # ── 누적 캔버스 ──
        blend_weight = _make_blend_weight(ps, overlap)
        blend_3ch = blend_weight[:, :, None]
        output_acc = np.zeros((out_h, out_w, 3), dtype=np.float32)
        input_acc = np.zeros((out_h, out_w, 3), dtype=np.float32)
        weight_acc = np.zeros((out_h, out_w), dtype=np.float32)

        tissue_count = 0
        bs = batch_size
        io_workers = min(max(2, os.cpu_count() or 4), 8)
        tissue_batch = []

        icc_tf = info.icc_transform
        with torch.inference_mode(), ThreadPoolExecutor(max_workers=io_workers) as pool:
            futures = []
            for (xi, yi, x0, y0, px, py_c, is_tissue) in all_patches:
                _check_cancel(task_id)
                wait_if_viewer_busy()
                f = pool.submit(_read_patch, slide_path, x0, y0,
                                best_level, level_read, ps, icc_tf, None)
                futures.append(f)

            for patch_idx, (xi, yi, x0, y0, px, py_c, is_tissue) in enumerate(all_patches):
                _check_cancel(task_id)
                region_np = futures[patch_idx].result()
                input_acc[py_c:py_c + ps, px:px + ps] += region_np * blend_3ch

                if not is_tissue:
                    output_acc[py_c:py_c + ps, px:px + ps] += region_np * blend_3ch
                    weight_acc[py_c:py_c + ps, px:px + ps] += blend_weight
                else:
                    t = torch.from_numpy(region_np).permute(2, 0, 1)
                    t = t / 255.0 * 2.0 - 1.0
                    tissue_batch.append((px, py_c, t))

                is_end_of_row = (xi == n_px - 1)
                batch_full = len(tissue_batch) >= bs
                if tissue_batch and (batch_full or is_end_of_row):
                    VirtualStainWorker._run_batch(
                        generator, device, use_fp16, tissue_batch,
                        output_acc, weight_acc, blend_3ch, blend_weight, ps,
                    )
                    tissue_count += len(tissue_batch)
                    tissue_batch.clear()

                if is_end_of_row:
                    pct = 8 + int(87 * (yi + 1) / n_py)
                    _update_task(task_id, progress=pct,
                                 status_msg=f"Virtual staining... row {yi + 1}/{n_py} "
                                            f"({tissue_count} tissue patches)")

        if tissue_batch:
            VirtualStainWorker._run_batch(
                generator, device, use_fp16, tissue_batch,
                output_acc, weight_acc, blend_3ch, blend_weight, ps,
            )
            tissue_count += len(tissue_batch)
            tissue_batch.clear()

        _check_cancel(task_id)
        _update_task(task_id, progress=96, status_msg="Composing final image...")

        # ── Compose ──
        uncovered = weight_acc < 0.01
        weight_acc = np.maximum(weight_acc, 1e-10)
        output_canvas = (output_acc / weight_acc[:, :, None]).clip(0, 255).astype(np.uint8)
        input_canvas = (input_acc / weight_acc[:, :, None]).clip(0, 255).astype(np.uint8)
        output_canvas[uncovered] = 255
        input_canvas[uncovered] = 255
        output_canvas[~tissue_pixel_mask] = input_canvas[~tissue_pixel_mask]

        # ── Polygon ROI 마스킹 → RGBA ──
        import cv2
        alpha = np.full((out_h, out_w), 255, dtype=np.uint8)
        if roi_polygons:
            scale_x = out_w / canvas_l0_w
            scale_y = out_h / canvas_l0_h
            poly_mask = np.zeros((out_h, out_w), dtype=np.uint8)
            for poly_coords in roi_polygons:
                pts = np.array([
                    [round((x - x_min) * scale_x), round((y - y_min) * scale_y)]
                    for x, y in poly_coords
                ], dtype=np.int32)
                cv2.fillPoly(poly_mask, [pts], 255)
            alpha = poly_mask

        rgba = np.dstack([output_canvas, alpha])

        # ── 캐시 저장 (전체 추론만 도달; ROI는 위에서 캐시 hit 또는 폴리곤 무시) ──
        levels_meta = []
        tile_size_px = 512
        try:
            _update_task(task_id, progress=97, status_msg="Saving composite PNG...")
            # 여기서 비로소 PNG/meta 가 새로 작성됨 → 취소 시에만 이 파일들 정리.
            # (타일 디렉터리는 아래 generate_vs_tiles 가 끝난 뒤에만 존재하며,
            #  그 단계엔 취소 체크포인트가 없으므로 정리 대상에 넣지 않는다.)
            list_cleanup_on_cancel.extend([png_path, meta_path])
            Image.fromarray(rgba, 'RGBA').save(str(png_path), format='PNG', optimize=False)

            _update_task(task_id, progress=98, status_msg="Generating tile pyramid...")
            tile_dir = _get_vs_tile_dir(info.file_path, stain_type, target_mpp)
            levels_meta = _generate_vs_tiles(
                output_canvas, tile_dir,
                tile_size=tile_size_px, n_levels=4,
            )

            meta = {
                "stain_type": stain_type,
                "roi_origin": [int(x_min), int(y_min)],
                "canvas_l0_w": int(canvas_l0_w),
                "canvas_l0_h": int(canvas_l0_h),
                "target_mpp": target_mpp,
                "tissue_count": int(tissue_count),
                "total_patches": int(n_px * n_py),
                "image_filename": png_path.name,
                "tile_size": tile_size_px,
                "levels": levels_meta,
            }
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f)
            print(f"VS result cached: {png_path} + {len(levels_meta)} pyramid levels")
            from app import slide_store
            slide_store.mark_ai_result_threadsafe(info.file_path, "VS-IHC", stain_type)
        except Exception as e:
            import traceback
            print(f"VS cache save failed: {e}\n{traceback.format_exc()}")

        result_payload = {
            "stain_type": stain_type,
            "image_filename": png_path.name,
            "roi_origin": [int(x_min), int(y_min)],
            "canvas_l0_w": int(canvas_l0_w),
            "canvas_l0_h": int(canvas_l0_h),
            "target_mpp": target_mpp,
            "tissue_count": int(tissue_count),
            "total_patches": int(n_px * n_py),
            "tile_size": tile_size_px,
            "levels": levels_meta,
            "cached": False,
        }
        if display_roi_polygons is not None:
            result_payload["roi_polygons"] = display_roi_polygons
        _update_task(task_id, status="completed", progress=100,
                     status_msg=f"Virtual staining complete — {tissue_count}/{n_px * n_py} patches",
                     result=result_payload)

        del generator
        slide.close()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    except TaskCancelled:
        _cleanup_cache_paths(list_cleanup_on_cancel)
        _update_task(task_id, status="cancelled", progress=0,
                     status_msg="Cancelled by user", error=None)
        print(f"[cancel] _run_virtual_stain cancelled task={task_id}")
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    except Exception as e:
        import traceback
        _update_task(task_id, status="error",
                     error=f"Virtual staining failed: {e}\n{traceback.format_exc()}")


@router.post("/virtual-stain")
async def start_virtual_stain(
    request: Request,
    slide_id: str = Form(...),
    stain_type: str = Form("ihc_membrane"),
    target_mpp: float = Form(2.0),
    roi_polygons: Optional[str] = Form(None),
    dict_user: dict = Depends(get_current_user),
):
    """Virtual stain (VS-IHC) 작업 시작 (비동기)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    if stain_type not in VS_MODEL_FILES:
        raise HTTPException(400, f"Unknown stain type: {stain_type}")

    polygons = json.loads(roi_polygons) if roi_polygons else None
    task_id = uuid.uuid4().hex[:12]
    str_filename = Path(info.file_path).name

    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued", "progress": 0,
            "result": None, "error": None, "status_msg": "",
            "slide_filename": str_filename,
            "model": "VS-IHC", "variant": stain_type,
        }

    t = threading.Thread(
        target=_run_virtual_stain,
        args=(task_id, slide_id, polygons, stain_type, target_mpp),
        daemon=True,
    )
    t.start()
    await _log_ai_analyze(request, dict_user, "VS-IHC", stain_type, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.get("/virtual-stain/{slide_id}/{stain_type}.png")
async def get_virtual_stain_image(slide_id: str, stain_type: str,
                                  target_mpp: float = Query(2.0)):
    """Virtual stain 캐시 PNG 서빙 (전체 추론 결과, PDF/리포트용)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    png_path, _ = _get_vs_cache_paths(info.file_path, stain_type, target_mpp)
    if not png_path.exists():
        raise HTTPException(404, "Virtual stain image not found")
    return FileResponse(str(png_path), media_type="image/png")


@media_router.get("/virtual-stain/{slide_id}/{stain_type}/tile/{level}/{tx}_{ty}.jpeg")
async def get_virtual_stain_tile(
    slide_id: str,
    stain_type: str,
    level: int,
    tx: int,
    ty: int,
    target_mpp: float = Query(2.0),
):
    """
    Virtual stain 피라미드 타일 서빙.
    디스크에 있으면 정적 서빙, 없으면 404 (빈/흰 타일은 생성 안 함).
    """
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    tile_dir = _get_vs_tile_dir(info.file_path, stain_type, target_mpp)
    tile_path = tile_dir / str(level) / f"{tx}_{ty}.jpeg"
    if not tile_path.exists():
        raise HTTPException(404, "tile not found")
    return FileResponse(
        str(tile_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )
