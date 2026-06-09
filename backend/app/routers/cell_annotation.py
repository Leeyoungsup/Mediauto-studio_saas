"""Patch-based cell annotation workflow endpoints."""

import asyncio
from datetime import datetime, timezone
import json
from math import ceil, floor
from pathlib import Path
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request

from app.auth import get_current_user, require_not_viewer, require_role
from app.database import get_db, is_db_connected
from app.models import UserRole
from app.path_utils import safe_filename, safe_subpath
from app.project_utils import (
    ANNOTATION_AI_OPTION_BY_KEY,
    ANNOTATION_AI_OPTIONS,
    OTHER_CELL_CLASS,
    cell_annotation_classes_for_ai,
    normalize_annotation_ai_config,
)
from app.slide_manager import slide_manager
from app.ai_pipelines.dedup import cache_has_current_detection_postprocess, processing_metadata
from app.ai_pipelines.detection import run_detection as _run_detection
from app.ai_pipelines.marker_pipeline import (
    run_pd_score as _run_pd_score,
    run_precise_ihc as _run_precise_ihc,
)
from app.ai_pipelines.task_state import _tasks, _tasks_lock, cleanup_old_tasks, release_task_result, update_task
from app.cell_annotation_utils import (
    bbox as _bbox,
    patch_key_from_xy as _patch_key_from_xy,
    poly_intersects_rect as _poly_intersects_rect,
    region_points as _region_points,
)
from app.config import settings
from app.cpu_layout import ai_executor, patch_executor


router = APIRouter(dependencies=[Depends(get_current_user)])

TARGET_MPP = 0.5
PATCH_PHYSICAL_UM = 512.0
TARGET_PATCH_SIZE = int(round(PATCH_PHYSICAL_UM / TARGET_MPP))
CELL_ANNOTATION_ROOT = Path(__file__).resolve().parents[2] / "cell_annotation"
ASSISTANCE_LABEL_SCHEMA = ["x", "y", "width", "height", "center_x", "center_y", "class_id", "confidence"]
PATCH_STATUSES = {
    "not_required",
    "required",
    "in_progress",
    "completed",
    "reviewed",
    "rejected",
}
REGION_TYPES = {"annotation_required_region", "annotation_excluded_region"}
DEFAULT_ASSISTANCE_BOX_SIZE = 32.0
CELL_CLASSES_MAX_BYTES = 256 * 1024
DEFAULT_CELL_CLASSES = [dict(OTHER_CELL_CLASS)]
_export_tasks: dict[str, asyncio.Task] = {}
_export_requested: set[str] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_db():
    if not is_db_connected():
        raise HTTPException(503, "Database is not connected")
    return get_db()


def _slide_info(slide_id: str):
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Slide not found")
    return info


def _patch_slide_size(info) -> int:
    mpp = float(getattr(info, "mpp", 0) or TARGET_MPP)
    if mpp <= 0:
        mpp = TARGET_MPP
    return max(1, int(round(TARGET_PATCH_SIZE * TARGET_MPP / mpp)))


def _safe_project_name(project_path: str) -> str:
    str_project = (project_path or "").replace("\\", "/").split("/")[0].strip()
    if not str_project:
        raise HTTPException(400, "Project path is required")
    str_project = safe_filename(str_project)
    project_dir = safe_subpath(str_project)
    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(404, "Project not found")
    return str_project


def _cell_project_classes_path(project_path: str) -> Path:
    return CELL_ANNOTATION_ROOT / "_projects" / _safe_project_name(project_path) / "classes.json"


def _normalize_cell_class_color(value) -> list[int]:
    if isinstance(value, str):
        raw = value.strip().lstrip("#")
        if len(raw) == 6:
            try:
                return [int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)]
            except Exception:
                pass
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        out = []
        for item in value[:3]:
            try:
                out.append(max(0, min(255, int(item))))
            except Exception:
                out.append(0)
        return out
    return [0, 255, 0]


def _normalize_cell_classes(value) -> list[dict]:
    if not isinstance(value, list):
        raise HTTPException(400, "cell annotation classes must be a list")
    classes = []
    seen = set()
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:64] or f"Class {idx}"
        raw_id = str(item.get("id") or name).strip()[:80]
        raw_id = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in raw_id)
        raw_id = raw_id.strip("_-") or f"class_{idx}"
        base_id = raw_id
        suffix = 2
        while raw_id in seen:
            raw_id = f"{base_id}_{suffix}"
            suffix += 1
        seen.add(raw_id)
        classes.append({
            "id": raw_id,
            "name": name,
            "color": _normalize_cell_class_color(item.get("color")),
        })
    return classes or list(DEFAULT_CELL_CLASSES)


def _merge_cell_classes(base_classes: list[dict], default_classes: list[dict]) -> list[dict]:
    default_names = {str(cls.get("name", "")).lower() for cls in (default_classes or []) if cls.get("name")}
    default_ids = {str(cls.get("id", "")) for cls in (default_classes or []) if cls.get("id") is not None}
    merged = [
        cls for cls in (base_classes or [])
        if str(cls.get("id", "")) in default_ids or str(cls.get("name", "")).lower() not in default_names
    ]
    seen_ids = {str(cls.get("id", "")) for cls in merged}
    for cls in default_classes or []:
        cls_id = str(cls.get("id", ""))
        if cls_id in seen_ids:
            continue
        merged.append(dict(cls))
        seen_ids.add(cls_id)
    has_other = any(str(cls.get("name", "")).lower() == "other" for cls in merged)
    if not has_other:
        other_id = str(OTHER_CELL_CLASS["id"])
        if other_id in seen_ids:
            other_id = "other_cell"
        merged.append({**OTHER_CELL_CLASS, "id": other_id})
    return merged or list(DEFAULT_CELL_CLASSES)


async def _project_ai_default_classes(project_path: str) -> list[dict]:
    if not project_path or not is_db_connected():
        return []
    project_name = (project_path or "").replace("\\", "/").split("/")[0].strip()
    doc = await get_db().project_infos.find_one({"str_project_path": project_name})
    return cell_annotation_classes_for_ai(
        bool((doc or {}).get("bool_annotation_ai_enabled", False)),
        str((doc or {}).get("str_annotation_ai_key", "")),
    )


def _load_cell_classes_for_project(project_path: str) -> list[dict]:
    if not project_path:
        return list(DEFAULT_CELL_CLASSES)
    try:
        class_path = _cell_project_classes_path(project_path)
        if not class_path.exists():
            return list(DEFAULT_CELL_CLASSES)
        payload = json.loads(class_path.read_text(encoding="utf-8"))
        classes = payload.get("classes") if isinstance(payload, dict) else payload
        return _normalize_cell_classes(classes)
    except HTTPException:
        raise
    except Exception:
        return list(DEFAULT_CELL_CLASSES)


def _patch_id_from_xy(x: int, y: int) -> str:
    return _patch_key_from_xy(x, y)


def _patch_num_from_id(value: str) -> Optional[int]:
    match = re.fullmatch(r"patch_(\d+)", str(value or ""))
    if not match:
        return None
    return int(match.group(1))


async def _next_patch_number(db, slide_id: str) -> int:
    cursor = db.patch_annotation_status.find(
        {"str_slide_id": slide_id, "str_patch_id": {"$regex": r"^patch_\d+$"}},
        {"str_patch_id": 1},
    )
    max_num = 0
    async for doc in cursor:
        num = _patch_num_from_id(doc.get("str_patch_id"))
        if num and num > max_num:
            max_num = num
    return max_num + 1


async def _patch_id_for_key(db, slide_id: str, patch_key: str, allocated: dict[str, str]) -> str:
    if patch_key in allocated:
        return allocated[patch_key]
    existing = await db.patch_annotation_status.find_one(
        {"str_slide_id": slide_id, "$or": [{"str_patch_key": patch_key}, {"str_patch_id": patch_key}]},
        {"str_patch_id": 1},
    )
    existing_id = str((existing or {}).get("str_patch_id") or "")
    if _patch_num_from_id(existing_id):
        allocated[patch_key] = existing_id
        return existing_id
    if "__next_num__" not in allocated:
        allocated["__next_num__"] = await _next_patch_number(db, slide_id)
    next_num = int(allocated["__next_num__"])
    patch_id = f"patch_{next_num}"
    allocated["__next_num__"] = next_num + 1
    allocated[patch_key] = patch_id
    return patch_id


def _patch_workflow_fields(status: str) -> dict:
    annotation_status = "pending"
    review_status = "pending"
    termination_status = "pending"
    if status == "required":
        annotation_status = "required"
    elif status == "in_progress":
        annotation_status = "in_progress"
    elif status == "completed":
        annotation_status = "completed"
        review_status = "current"
    elif status == "reviewed":
        annotation_status = "completed"
        review_status = "reviewed"
        termination_status = "current"
    elif status == "rejected":
        annotation_status = "completed"
        review_status = "rejected"
        termination_status = "current"
    elif status == "not_required":
        annotation_status = "not_required"
    return {
        "str_annotation_status": annotation_status,
        "str_review_status": review_status,
        "str_termination_status": termination_status,
    }


def _patch_doc(slide_id: str, px: int, py: int, status: str, info, user: dict, patch_id: str = "") -> dict:
    patch_size = _patch_slide_size(info)
    x0 = px * patch_size
    y0 = py * patch_size
    w, h = info.dimensions
    patch_key = _patch_key_from_xy(x0, y0)
    return {
        "str_slide_id": slide_id,
        "str_patch_id": patch_id or patch_key,
        "str_patch_key": patch_key,
        "int_px": int(px),
        "int_py": int(py),
        "int_x": int(x0),
        "int_y": int(y0),
        "int_w": int(max(0, min(patch_size, w - x0))),
        "int_h": int(max(0, min(patch_size, h - y0))),
        "str_status": status,
        **_patch_workflow_fields(status),
        "str_updated_by": str(user.get("_id", "")),
        "dt_updated_at": _now(),
    }


def _normalize_region(item: dict, idx: int) -> dict:
    points = _region_points(item)
    if len(points) < 3:
        raise HTTPException(400, "Required region must contain at least three points")
    bbox = _bbox(points)
    region_type = str(
        item.get("type")
        or item.get("region_type")
        or item.get("str_type")
        or "annotation_required_region"
    )
    if region_type not in REGION_TYPES:
        raise HTTPException(400, f"Invalid region type: {region_type}")
    return {
        "str_region_id": str(item.get("id") or item.get("region_id") or f"region_{idx}"),
        "str_type": region_type,
        "list_points": points,
        "dict_bbox": {
            "x0": bbox[0],
            "y0": bbox[1],
            "x1": bbox[2],
            "y1": bbox[3],
        },
    }


def _normalize_cell(cell: dict, patch: dict) -> dict:
    x = float(cell.get("x", cell.get("slide_x", 0)))
    y = float(cell.get("y", cell.get("slide_y", 0)))
    out = {
        "id": str(cell.get("id") or ""),
        "x": x,
        "y": y,
        "local_x": float(cell.get("local_x", x - patch["int_x"])),
        "local_y": float(cell.get("local_y", y - patch["int_y"])),
        "class_id": cell.get("class_id", cell.get("classId", "")),
        "class_name": str(cell.get("class_name", cell.get("className", ""))),
        "confidence": float(cell.get("confidence", 1.0)),
        "source": str(cell.get("source", "manual")),
    }
    shape_type = str(cell.get("shape_type") or cell.get("type") or "").strip()
    if shape_type:
        out["shape_type"] = shape_type
        out["type"] = shape_type

    def _normalize_points(value) -> list[list[float]]:
        if not isinstance(value, list):
            return []
        points = []
        for point in value:
            try:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    px = float(point[0])
                    py = float(point[1])
                elif isinstance(point, dict):
                    px = float(point.get("x"))
                    py = float(point.get("y"))
                else:
                    continue
            except Exception:
                continue
            points.append([px, py])
        return points

    points = _normalize_points(cell.get("coordinates") or cell.get("points") or cell.get("list_points"))
    if points:
        out["coordinates"] = points
        local_points = _normalize_points(cell.get("local_coordinates") or cell.get("local_points"))
        if not local_points:
            local_points = [[px - float(patch["int_x"]), py - float(patch["int_y"])] for px, py in points]
        out["local_coordinates"] = local_points

    raw_bbox = cell.get("bbox") if isinstance(cell.get("bbox"), dict) else {}
    try:
        bx0 = float(raw_bbox.get("x0", raw_bbox.get("x", cell.get("x0"))))
        by0 = float(raw_bbox.get("y0", raw_bbox.get("y", cell.get("y0"))))
        bw = float(raw_bbox.get("width", cell.get("width", 0)))
        bh = float(raw_bbox.get("height", cell.get("height", 0)))
        bx1 = float(raw_bbox.get("x1", cell.get("x1", bx0 + bw)))
        by1 = float(raw_bbox.get("y1", cell.get("y1", by0 + bh)))
        if bw <= 0:
            bw = max(1.0, bx1 - bx0)
        if bh <= 0:
            bh = max(1.0, by1 - by0)
        if bx1 <= bx0:
            bx1 = bx0 + bw
        if by1 <= by0:
            by1 = by0 + bh
        out["bbox"] = {
            "x": bx0,
            "y": by0,
            "width": bw,
            "height": bh,
            "x0": bx0,
            "y0": by0,
            "x1": bx1,
            "y1": by1,
        }
    except Exception:
        if points:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            bx0 = min(xs)
            by0 = min(ys)
            bx1 = max(xs)
            by1 = max(ys)
            out["bbox"] = {
                "x": bx0,
                "y": by0,
                "width": max(1.0, bx1 - bx0),
                "height": max(1.0, by1 - by0),
                "x0": bx0,
                "y0": by0,
                "x1": bx1,
                "y1": by1,
            }
    return out


def _normalize_memo_history(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            answer = ""
            accepted_at = ""
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("memo") or "").strip()
            answer = str(item.get("answer") or item.get("reply") or "").strip()
            accepted_at = str(item.get("accepted_at") or item.get("created_at") or "").strip()
        else:
            continue
        if text:
            out.append({
                "text": text[:2000],
                "answer": answer[:2000],
                "accepted_at": accepted_at[:80],
            })
    return out[:200]


def _cell_annotation_slide_dir(info) -> Path:
    return CELL_ANNOTATION_ROOT / Path(info.file_path).stem


def _slide_project_path(info) -> str:
    try:
        rel = Path(info.file_path).resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
        return rel.parts[0] if rel.parts else ""
    except Exception:
        return ""


def _assistance_path(info) -> Path:
    return _cell_annotation_slide_dir(info) / "WSI_Labeling_assistance.json"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _write_compact_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=_json_default),
        encoding="utf-8",
    )


def _cell_annotation_info_payload(slide_id: str, info, info_patches: list[dict]) -> dict:
    return {
        "slide_id": slide_id,
        "slide_filename": Path(info.file_path).name,
        "slide_stem": Path(info.file_path).stem,
        "target_mpp": TARGET_MPP,
        "target_patch_size": TARGET_PATCH_SIZE,
        "patch_physical_um": PATCH_PHYSICAL_UM,
        "slide_mpp": getattr(info, "mpp", None),
        "patch_size_slide_px": _patch_slide_size(info),
        "classes": _load_cell_classes_for_project(_slide_project_path(info)),
        "patches": info_patches,
    }


def _write_cell_annotation_info(slide_id: str, info, info_patches: Optional[list[dict]] = None) -> None:
    root = _cell_annotation_slide_dir(info)
    (root / "patches").mkdir(parents=True, exist_ok=True)
    (root / "labels").mkdir(parents=True, exist_ok=True)
    _write_json(root / "info.json", _cell_annotation_info_payload(slide_id, info, info_patches or []))


async def _ensure_cell_annotation_layout(slide_id: str, info) -> None:
    info_patches = []
    if is_db_connected():
        db = get_db()
        patches = await db.patch_annotation_status.find(
            {"str_slide_id": slide_id, "str_status": {"$ne": "not_required"}},
            {"_id": 0},
        ).sort([("int_py", 1), ("int_px", 1)]).to_list(length=200000)
        for patch in patches:
            patch_id = patch.get("str_patch_id")
            if not patch_id:
                continue
            info_patches.append({
                "patch_id": patch_id,
                "patch_key": patch.get("str_patch_key", ""),
                "grid_x": patch.get("int_px"),
                "grid_y": patch.get("int_py"),
                "x": patch.get("int_x"),
                "y": patch.get("int_y"),
                "width": patch.get("int_w"),
                "height": patch.get("int_h"),
                "status": patch.get("str_status"),
                "annotation_status": patch.get("str_annotation_status"),
                "review_status": patch.get("str_review_status"),
                "termination_status": patch.get("str_termination_status"),
                "memo": patch.get("str_memo", ""),
            })
    _write_cell_annotation_info(slide_id, info, info_patches)


def _write_patch_image(info, patch: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import openslide
        from app import tile_generator
        from app.ndp_color_match import apply_ndp_fit, is_hamamatsu_slide
        from app.slide_manager import build_color_corrector

        slide = openslide.OpenSlide(info.file_path)
        image = None
        image_rgb = None
        image_color = None
        image_out = None
        try:
            x = int(patch.get("int_x", 0))
            y = int(patch.get("int_y", 0))
            w = max(1, int(patch.get("int_w", 0)))
            h = max(1, int(patch.get("int_h", 0)))
            image = slide.read_region((x, y), 0, (w, h))
            image_rgb = tile_generator.image_to_white_rgb(image)
            apply_color, _ = build_color_corrector(slide)
            image_color = apply_color(image_rgb)

            # Viewer paths auto-use the NDP-matched variant for Hamamatsu/NDPI.
            # Exported patch JPEGs should match that visual pipeline, too.
            suffix = Path(info.file_path).suffix.lower()
            if suffix == ".ndpi" or is_hamamatsu_slide(slide.properties):
                image_out = apply_ndp_fit(image_color)
            else:
                image_out = image_color

            image_out.save(out_path, "JPEG", quality=90, optimize=True)
        finally:
            for obj in (image_out, image_color, image_rgb, image):
                try:
                    if obj is not None:
                        obj.close()
                except Exception:
                    pass
            slide.close()
    except Exception as exc:
        print(f"[cell_annotation] patch image export failed ({out_path.name}): {exc}")


async def _export_cell_annotation_files(slide_id: str, info, regions: list[dict]) -> None:
    db = _require_db()
    root = _cell_annotation_slide_dir(info)
    patches_dir = root / "patches"
    labels_dir = root / "labels"
    patches_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    await db.patch_annotation_status.delete_many({"str_slide_id": slide_id, "str_status": "not_required"})
    patches = await db.patch_annotation_status.find(
        {"str_slide_id": slide_id, "str_status": {"$ne": "not_required"}},
        {"_id": 0},
    ).sort([("int_py", 1), ("int_px", 1)]).to_list(length=200000)

    active_ids = {
        p.get("str_patch_id")
        for p in patches
        if p.get("str_patch_id")
    }
    for path in patches_dir.glob("patch_*.jpeg"):
        if path.stem not in active_ids:
            path.unlink(missing_ok=True)
    for path in labels_dir.glob("patch_*.json"):
        if path.stem not in active_ids:
            path.unlink(missing_ok=True)

    info_patches = []
    for patch in patches:
        patch_id = patch.get("str_patch_id")
        if not patch_id:
            continue
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            patch_executor,
            _write_patch_image,
            info,
            patch,
            patches_dir / f"{patch_id}.jpeg",
        )
        cells_doc = await db.patch_cell_annotations.find_one(
            {"str_slide_id": slide_id, "str_patch_id": patch_id},
            {"_id": 0},
        )
        label_path = labels_dir / f"{patch_id}.json"
        if cells_doc or not label_path.exists():
            _write_json(label_path, {
                "slide_id": slide_id,
                "patch_id": patch_id,
                "patch_key": patch.get("str_patch_key", ""),
                "cells": (cells_doc or {}).get("list_cells", []),
            })
        info_patches.append({
            "patch_id": patch_id,
            "patch_key": patch.get("str_patch_key", ""),
            "grid_x": patch.get("int_px"),
            "grid_y": patch.get("int_py"),
            "x": patch.get("int_x"),
            "y": patch.get("int_y"),
            "width": patch.get("int_w"),
            "height": patch.get("int_h"),
            "status": patch.get("str_status"),
            "annotation_status": patch.get("str_annotation_status"),
            "review_status": patch.get("str_review_status"),
            "termination_status": patch.get("str_termination_status"),
            "memo": patch.get("str_memo", ""),
        })

    _write_cell_annotation_info(slide_id, info, info_patches)
    (root / "WSI_regions.json").unlink(missing_ok=True)


async def _cell_annotation_export_worker(slide_id: str) -> None:
    try:
        while slide_id in _export_requested:
            _export_requested.discard(slide_id)
            await asyncio.sleep(0.05)
            try:
                info = _slide_info(slide_id)
                await _export_cell_annotation_files(slide_id, info, [])
            except Exception as exc:
                print(f"[cell_annotation] background export failed ({slide_id}): {exc}")
    finally:
        task = _export_tasks.get(slide_id)
        if task is asyncio.current_task():
            _export_tasks.pop(slide_id, None)


def _schedule_cell_annotation_export(slide_id: str) -> None:
    _export_requested.add(slide_id)
    task = _export_tasks.get(slide_id)
    if task and not task.done():
        return
    _export_tasks[slide_id] = asyncio.create_task(_cell_annotation_export_worker(slide_id))


def _clear_cell_annotation_patch_files(slide_id: str, info) -> dict:
    root = _cell_annotation_slide_dir(info)
    counts = {"patch_images": 0, "label_files": 0}
    for subdir, key in (("patches", "patch_images"), ("labels", "label_files")):
        path_dir = root / subdir
        if not path_dir.exists():
            path_dir.mkdir(parents=True, exist_ok=True)
            continue
        for path in path_dir.iterdir():
            if not path.is_file():
                continue
            try:
                path.unlink()
                counts[key] += 1
            except Exception:
                pass
    (root / "WSI_regions.json").unlink(missing_ok=True)
    _write_cell_annotation_info(slide_id, info, [])
    return counts


async def _project_annotation_ai_config(info) -> dict:
    project_path = _slide_project_path(info)
    if not project_path or not is_db_connected():
        return {"enabled": False, "key": "", "label": ""}
    doc = await get_db().project_infos.find_one({"str_project_path": project_path})
    return normalize_annotation_ai_config(
        bool((doc or {}).get("bool_annotation_ai_enabled", False)),
        (doc or {}).get("str_annotation_ai_key", ""),
    )


def _read_assistance_file(info) -> dict:
    path = _assistance_path(info)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    compacted, changed = _compact_assistance_payload(payload)
    source_postprocess = compacted.get("source_ai_postprocess")
    if not cache_has_current_detection_postprocess(source_postprocess):
        try:
            path.unlink()
        except Exception as exc:
            print(f"[cell_annotation] stale assistance cleanup failed: {exc}")
        return {}
    config = compacted.get("annotation_ai") if isinstance(compacted.get("annotation_ai"), dict) else {}
    if config.get("enabled"):
        project_classes = _load_cell_classes_for_project(_slide_project_path(info))
        default_classes = cell_annotation_classes_for_ai(True, str(config.get("key", "")))
        merged_classes = _merge_cell_classes(project_classes, default_classes)
        current_classes = compacted.get("classes")
        if current_classes != merged_classes:
            compacted = dict(compacted)
            compacted["classes"] = merged_classes
            changed = True
    if changed:
        try:
            _write_compact_json(path, compacted)
        except Exception as exc:
            print(f"[cell_annotation] assistance compact rewrite failed: {exc}")
    return compacted


def _compact_assistance_label(label: Any) -> Optional[list]:
    if isinstance(label, (list, tuple)) and len(label) >= 8:
        try:
            return [
                round(float(label[0]), 2),
                round(float(label[1]), 2),
                round(float(label[2]), 2),
                round(float(label[3]), 2),
                round(float(label[4]), 2),
                round(float(label[5]), 2),
                str(label[6] or ""),
                round(float(label[7]), 4),
            ]
        except Exception:
            return None
    if not isinstance(label, dict):
        return None
    try:
        return [
            round(float(label.get("x", 0.0)), 2),
            round(float(label.get("y", 0.0)), 2),
            round(float(label.get("width", 0.0)), 2),
            round(float(label.get("height", 0.0)), 2),
            round(float(label.get("center_x", 0.0)), 2),
            round(float(label.get("center_y", 0.0)), 2),
            str(label.get("class_id", "") or ""),
            round(float(label.get("confidence", 0.0)), 4),
        ]
    except Exception:
        return None


def _compact_assistance_payload(payload: dict) -> tuple[dict, bool]:
    if not isinstance(payload, dict):
        return {}, False
    labels = payload.get("labels")
    if not isinstance(labels, list):
        return payload, False
    annotation_ai = payload.get("annotation_ai") if isinstance(payload.get("annotation_ai"), dict) else {}
    use_other_class = annotation_ai.get("inherit_classes") is False
    already_compact = payload.get("label_format") == "bbox_compact_v1" and (
        not labels or isinstance(labels[0], list)
    )
    if already_compact:
        changed = False
        if use_other_class:
            next_labels = []
            for label in labels:
                if isinstance(label, list) and len(label) >= 7 and not str(label[6] or "").strip():
                    label = [*label]
                    label[6] = str(OTHER_CELL_CLASS.get("id", "other"))
                    changed = True
                next_labels.append(label)
            if changed:
                payload = dict(payload)
                payload["labels"] = next_labels
        payload["total_labels"] = len(payload.get("labels") or [])
        payload["total_model_bbox_labels"] = int(payload.get("total_model_bbox_labels") or payload["total_labels"])
        return payload, changed
    compact_labels = []
    for label in labels:
        compact = _compact_assistance_label(label)
        if compact is not None:
            if use_other_class and not str(compact[6] or "").strip():
                compact[6] = str(OTHER_CELL_CLASS.get("id", "other"))
            compact_labels.append(compact)
    compacted = dict(payload)
    compacted["labels"] = compact_labels
    compacted["label_format"] = "bbox_compact_v1"
    compacted["label_schema"] = ASSISTANCE_LABEL_SCHEMA
    compacted["bbox_source"] = "model" if compact_labels else ""
    compacted["total_labels"] = len(compact_labels)
    compacted["total_model_bbox_labels"] = len(compact_labels)
    compacted.pop("fallback_bbox_size_px", None)
    return compacted, True


def _assistance_metadata(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    meta = {k: v for k, v in payload.items() if k != "labels"}
    labels = payload.get("labels")
    meta["total_labels"] = len(labels) if isinstance(labels, list) else int(meta.get("total_labels") or 0)
    if "total_model_bbox_labels" not in meta:
        meta["total_model_bbox_labels"] = meta["total_labels"] if meta.get("base_result_format") == "bbox" else 0
    return meta


def _assistance_class_lookup(info, payload: Optional[dict] = None) -> dict[str, dict]:
    classes = _load_cell_classes_for_project(_slide_project_path(info))
    payload_classes = (payload or {}).get("classes") if isinstance(payload, dict) else None
    if isinstance(payload_classes, list):
        classes = _merge_cell_classes(classes, payload_classes)
    lookup = {str(cls.get("id", "")): cls for cls in classes if cls.get("id") is not None}
    other = next((cls for cls in classes if str(cls.get("name", "")).lower() == "other"), None)
    if other:
        lookup.setdefault("", other)
    return lookup


def _assistance_label_to_cell(label: Any, patch: dict, idx: int, class_lookup: dict[str, dict]) -> Optional[dict]:
    compact = _compact_assistance_label(label)
    if compact is None:
        return None
    x, y, width, height, center_x, center_y, class_id, confidence = compact
    patch_x = float(patch.get("int_x", 0))
    patch_y = float(patch.get("int_y", 0))
    patch_w = float(patch.get("int_w", 0))
    patch_h = float(patch.get("int_h", 0))
    if center_x < patch_x or center_x >= patch_x + patch_w or center_y < patch_y or center_y >= patch_y + patch_h:
        return None
    class_meta = class_lookup.get(str(class_id)) or class_lookup.get("") or {}
    effective_class_id = str(class_meta.get("id", class_id or ""))
    class_name = str(class_meta.get("name", ""))
    color = class_meta.get("color")
    x1 = x + max(1.0, width)
    y1 = y + max(1.0, height)
    return {
        "id": f"assist_{idx}",
        "type": "rectangle",
        "shape_type": "rectangle",
        "x": center_x,
        "y": center_y,
        "local_x": center_x - patch_x,
        "local_y": center_y - patch_y,
        "coordinates": [[x, y], [x1, y], [x1, y1], [x, y1]],
        "local_coordinates": [[x - patch_x, y - patch_y], [x1 - patch_x, y - patch_y], [x1 - patch_x, y1 - patch_y], [x - patch_x, y1 - patch_y]],
        "bbox": {
            "x": x,
            "y": y,
            "width": max(1.0, width),
            "height": max(1.0, height),
            "x0": x,
            "y0": y,
            "x1": x1,
            "y1": y1,
        },
        "class_id": effective_class_id,
        "class_name": class_name,
        "color": color,
        "confidence": confidence,
        "source": "wsi_labeling_assistance",
    }


def _model_class_metadata_for_assistance(config: dict) -> tuple[dict[str, str], dict[str, str]]:
    base_model = config.get("base_model")
    variant = config.get("variant")
    if base_model == "Quanti HE":
        from ai.quanti_he import CLASS_COLORS, CLASS_NAMES

        return (
            {str(k): str(v) for k, v in CLASS_NAMES.items()},
            {str(k): str(v) for k, v in CLASS_COLORS.items()},
        )
    if base_model == "Quanti PD-L1":
        from app.ai_pipelines.scoring import PD_SCORE_CONFIG

        model = PD_SCORE_CONFIG.get(variant) or {}
        return (
            {str(k): str(v) for k, v in (model.get("class_names") or {}).items()},
            {str(k): str(v) for k, v in (model.get("class_colors") or {}).items()},
        )
    if base_model == "Quanti IHC":
        from app.ai_pipelines.scoring import PRECISE_IHC_CONFIG

        model = PRECISE_IHC_CONFIG.get(variant) or {}
        return (
            {str(k): str(v) for k, v in (model.get("class_names") or {}).items()},
            {str(k): str(v) for k, v in (model.get("class_colors") or {}).items()},
        )
    return {}, {}


def _cell_tuple_values(cell) -> Optional[tuple[float, float, Any, float, Optional[tuple[float, float, float, float]]]]:
    bbox = None
    if isinstance(cell, dict):
        x = cell.get("x", cell.get("slide_x"))
        y = cell.get("y", cell.get("slide_y"))
        class_id = cell.get("class_id", cell.get("classId"))
        confidence = cell.get("confidence", 1.0)
        if all(k in cell for k in ("x0", "y0", "x1", "y1")):
            bbox = (cell.get("x0"), cell.get("y0"), cell.get("x1"), cell.get("y1"))
    elif isinstance(cell, (list, tuple)) and len(cell) >= 4:
        x, y, class_id, confidence = cell[:4]
        if len(cell) >= 8 and all(isinstance(cell[i], (int, float)) for i in range(4, 8)):
            bbox = tuple(cell[4:8])
    else:
        return None
    try:
        parsed_bbox = None
        if bbox is not None:
            parsed_bbox = tuple(float(v) for v in bbox)
        return float(x), float(y), class_id, float(confidence), parsed_bbox
    except Exception:
        return None


def _result_cells_to_bbox_labels(result: dict, config: dict) -> list[dict]:
    class_names = result.get("class_names") if isinstance(result, dict) else {}
    if not isinstance(class_names, dict):
        class_names = {}
    model_class_names, _ = _model_class_metadata_for_assistance(config)
    class_names = {
        **{str(k): str(v) for k, v in class_names.items()},
        **model_class_names,
    }
    inherit_classes = bool(config.get("inherit_classes"))
    default_class_id = str(OTHER_CELL_CLASS.get("id", "other"))
    default_class_name = str(OTHER_CELL_CLASS.get("name", "Other"))
    labels = []
    used_model_bbox = False
    source_cells = list((result or {}).get("cells") or [])
    source_cells.extend(list((result or {}).get("excluded_cells") or []))
    for idx, cell in enumerate(source_cells, start=1):
        parsed = _cell_tuple_values(cell)
        if parsed is None:
            continue
        x, y, class_id, confidence, bbox = parsed
        if bbox is None:
            half = DEFAULT_ASSISTANCE_BOX_SIZE / 2.0
            x0, y0, x1, y1 = x - half, y - half, x + half, y + half
        else:
            x0, y0, x1, y1 = bbox
            used_model_bbox = True
        str_class_id = str(class_id)
        label_class_id = str_class_id if inherit_classes else default_class_id
        label_class_name = str(class_names.get(str_class_id, "")) if inherit_classes else default_class_name
        labels.append({
            "id": f"assist_{idx}",
            "x": round(x0, 2),
            "y": round(y0, 2),
            "width": round(max(0.0, x1 - x0), 2),
            "height": round(max(0.0, y1 - y0), 2),
            "center_x": round(x, 2),
            "center_y": round(y, 2),
            "class_id": label_class_id,
            "class_name": label_class_name,
            "confidence": round(confidence, 4),
            "source_format": "bbox",
            "bbox_source": "model" if bbox is not None else "fallback_point",
        })
    return labels, used_model_bbox


def _write_assistance_result(slide_id: str, info, config: dict, result: dict) -> dict:
    if not cache_has_current_detection_postprocess(result):
        raise ValueError(
            "Labeling assistance requires current Quanti AI post-processing. "
            "Remove the stale AI result cache and rerun annotation assistance."
        )
    labels, used_model_bbox = _result_cells_to_bbox_labels(result, config)
    if labels and not used_model_bbox:
        raise ValueError(
            "Labeling assistance requires model bbox output, but the AI result only contains points. "
            "Remove the stale AI result cache and rerun annotation assistance."
        )
    compact_labels = [_compact_assistance_label(label) for label in labels]
    compact_labels = [label for label in compact_labels if label is not None]
    project_classes = _load_cell_classes_for_project(_slide_project_path(info))
    default_classes = cell_annotation_classes_for_ai(bool(config.get("enabled")), str(config.get("key", "")))
    payload = {
        "slide_id": slide_id,
        "slide_filename": Path(info.file_path).name,
        "slide_stem": Path(info.file_path).stem,
        "generated_at": _now().isoformat(),
        "annotation_ai": config,
        "source_ai_postprocess": {
            "patch_overlap_um": result.get("patch_overlap_um"),
            "global_dedup_version": result.get("global_dedup_version"),
            "global_nms_iou_threshold": result.get("global_nms_iou_threshold"),
            "global_dedup_match_rule": result.get("global_dedup_match_rule"),
        },
        "required_ai_postprocess": processing_metadata(),
        "classes": _merge_cell_classes(project_classes, default_classes),
        "base_result_format": "bbox",
        "label_format": "bbox_compact_v1",
        "label_schema": ASSISTANCE_LABEL_SCHEMA,
        "bbox_source": "model" if used_model_bbox else "",
        "total_labels": len(compact_labels),
        "total_model_bbox_labels": len(compact_labels) if used_model_bbox else 0,
        "labels": compact_labels,
    }
    _write_compact_json(_assistance_path(info), payload)
    return payload


def _run_labeling_assistance_task(task_id: str, slide_id: str, file_path: str, config: dict) -> None:
    info = slide_manager.get(slide_id)
    if not info:
        try:
            info = slide_manager.open(slide_id, file_path)
        except Exception as exc:
            update_task(task_id, status="error", error=str(exc), progress=0)
            return
    try:
        update_task(task_id, status="running", progress=1, status_msg="Starting labeling assistance")
        base_model = config.get("base_model")
        variant = config.get("variant")
        if base_model == "Quanti HE":
            _run_detection(task_id, slide_id, None, variant)
        elif base_model == "Quanti PD-L1":
            _run_pd_score(task_id, slide_id, None, variant)
        elif base_model == "Quanti IHC":
            _run_precise_ihc(task_id, slide_id, None, variant)
        else:
            raise ValueError(f"Unsupported annotation AI model: {base_model}")
        with _tasks_lock:
            task = _tasks.get(task_id) or {}
            result = task.get("result")
            error = task.get("error")
        if not result:
            raise ValueError(error or "Labeling assistance model returned no result")
        payload = _write_assistance_result(slide_id, info, config, result)
        with _tasks_lock:
            if task_id in _tasks:
                _tasks[task_id].update({
                    "status": "completed",
                    "progress": 100,
                    "status_msg": "Labeling assistance ready",
                    "result": {
                        "status": "saved",
                        "path": str(_assistance_path(info)),
                        "total_labels": payload.get("total_labels", 0),
                    },
                    "updated_at": datetime.now(timezone.utc).timestamp(),
                })
    except Exception as exc:
        update_task(task_id, status="error", error=str(exc), progress=0)


@router.get("/classes")
async def load_cell_annotation_classes(path: str = Query(..., description="project path or current folder path")):
    class_path = _cell_project_classes_path(path)
    ai_defaults = await _project_ai_default_classes(path)
    if not class_path.exists():
        return {"classes": _merge_cell_classes([], ai_defaults)}
    try:
        payload = json.loads(class_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"Invalid cell annotation class JSON: {exc}")
    classes = payload.get("classes") if isinstance(payload, dict) else payload
    normalized = _normalize_cell_classes(classes)
    merged = _merge_cell_classes(normalized, ai_defaults)
    if merged != normalized:
        try:
            class_path.write_text(json.dumps({"classes": merged}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[cell_annotation] class defaults merge failed: {exc}")
    return {"classes": merged}


@router.post("/classes", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def save_cell_annotation_classes(
    request: Request,
    path: str = Form(...),
    data: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    if len(data.encode("utf-8")) > CELL_CLASSES_MAX_BYTES:
        raise HTTPException(413, "cell annotation class data is too large")
    try:
        payload = json.loads(data)
    except Exception as exc:
        raise HTTPException(400, f"Invalid cell annotation class JSON: {exc}")
    classes = _normalize_cell_classes(payload.get("classes") if isinstance(payload, dict) else payload)
    ai_defaults = await _project_ai_default_classes(path)
    classes = _merge_cell_classes(classes, ai_defaults)
    class_path = _cell_project_classes_path(path)
    class_path.parent.mkdir(parents=True, exist_ok=True)
    class_path.write_text(json.dumps({"classes": classes}, ensure_ascii=False, indent=2), encoding="utf-8")

    from app.routers.slides import _log_management_event

    str_project_id = _safe_project_name(path)
    await _log_management_event(
        request,
        dict_user,
        str_action="cell_annotation_classes.update",
        str_resource_type="project",
        str_resource_id=str_project_id,
        str_detail=f"Updated cell annotation classes for {str_project_id}",
        dict_after={"classes": classes},
    )
    return {"status": "saved", "count": len(classes), "classes": classes}


@router.get("/{slide_id}/grid-config")
async def get_grid_config(slide_id: str):
    info = _slide_info(slide_id)
    await _ensure_cell_annotation_layout(slide_id, info)
    patch_size = _patch_slide_size(info)
    width, height = info.dimensions
    return {
        "slide_id": slide_id,
        "target_mpp": TARGET_MPP,
        "target_patch_size": TARGET_PATCH_SIZE,
        "patch_physical_um": PATCH_PHYSICAL_UM,
        "slide_mpp": info.mpp,
        "patch_size_slide_px": patch_size,
        "slide_width": width,
        "slide_height": height,
        "cols": ceil(width / patch_size),
        "rows": ceil(height / patch_size),
    }


@router.post("/{slide_id}/required-regions", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def save_required_regions(
    slide_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    info = _slide_info(slide_id)
    db = _require_db()
    raw_regions = payload.get("regions", payload if isinstance(payload, list) else [])
    if not isinstance(raw_regions, list):
        raise HTTPException(400, "regions must be a list")
    regions = [_normalize_region(item, idx) for idx, item in enumerate(raw_regions, start=1)]
    now = _now()
    doc = {
        "str_slide_id": slide_id,
        "list_regions": regions,
        "str_updated_by": str(user.get("_id", "")),
        "dt_updated_at": now,
    }
    await db.annotation_required_regions.update_one(
        {"str_slide_id": slide_id},
        {"$set": doc, "$setOnInsert": {"dt_created_at": now}},
        upsert=True,
    )
    (_cell_annotation_slide_dir(info) / "WSI_regions.json").unlink(missing_ok=True)
    return {"status": "saved", "count": len(regions), "regions": regions}


@router.get("/{slide_id}/required-regions")
async def get_required_regions(slide_id: str):
    _slide_info(slide_id)
    db = _require_db()
    doc = await db.annotation_required_regions.find_one({"str_slide_id": slide_id}, {"_id": 0})
    return {"slide_id": slide_id, "regions": (doc or {}).get("list_regions", [])}


@router.post("/{slide_id}/patches/recompute-status", dependencies=[Depends(require_not_viewer)])
async def recompute_patch_status(slide_id: str, user: dict = Depends(get_current_user)):
    if user.get("str_role") == UserRole.LABELER.value:
        raise HTTPException(403, "Labeler role cannot change WSI-level required regions")
    info = _slide_info(slide_id)
    db = _require_db()
    region_doc = await db.annotation_required_regions.find_one({"str_slide_id": slide_id}, {"_id": 0})
    regions = (region_doc or {}).get("list_regions", [])
    await db.patch_annotation_status.delete_many({"str_slide_id": slide_id, "str_status": "not_required"})
    include_regions = [region for region in regions if region.get("str_type") != "annotation_excluded_region"]
    exclude_regions = [region for region in regions if region.get("str_type") == "annotation_excluded_region"]
    patch_size = _patch_slide_size(info)
    width, height = info.dimensions
    ops = []
    required_keys = set()
    allocated_ids: dict[str, str] = {}
    for region in include_regions:
        poly = region.get("list_points") or []
        box = _bbox(poly)
        if not box:
            continue
        x0, y0, x1, y1 = box
        px0 = max(0, floor(x0 / patch_size))
        py0 = max(0, floor(y0 / patch_size))
        px1 = min(ceil(width / patch_size) - 1, floor(x1 / patch_size))
        py1 = min(ceil(height / patch_size) - 1, floor(y1 / patch_size))
        for py in range(py0, py1 + 1):
            for px in range(px0, px1 + 1):
                rx0 = px * patch_size
                ry0 = py * patch_size
                rx1 = min(width, rx0 + patch_size)
                ry1 = min(height, ry0 + patch_size)
                if not _poly_intersects_rect(poly, rx0, ry0, rx1, ry1):
                    continue
                patch_key = _patch_key_from_xy(rx0, ry0)
                if patch_key in required_keys:
                    continue
                existing = await db.patch_annotation_status.find_one(
                    {"str_slide_id": slide_id, "$or": [{"str_patch_key": patch_key}, {"str_patch_id": patch_key}]},
                    {"str_status": 1, "str_patch_id": 1},
                )
                required_keys.add(patch_key)
                patch_id = await _patch_id_for_key(db, slide_id, patch_key, allocated_ids)
                status = (existing or {}).get("str_status") or "required"
                if status == "not_required":
                    status = "required"
                ops.append(_patch_doc(slide_id, px, py, status, info, user, patch_id=patch_id))

    excluded_keys = set()
    for region in exclude_regions:
        poly = region.get("list_points") or []
        box = _bbox(poly)
        if not box:
            continue
        x0, y0, x1, y1 = box
        px0 = max(0, floor(x0 / patch_size))
        py0 = max(0, floor(y0 / patch_size))
        px1 = min(ceil(width / patch_size) - 1, floor(x1 / patch_size))
        py1 = min(ceil(height / patch_size) - 1, floor(y1 / patch_size))
        for py in range(py0, py1 + 1):
            for px in range(px0, px1 + 1):
                rx0 = px * patch_size
                ry0 = py * patch_size
                rx1 = min(width, rx0 + patch_size)
                ry1 = min(height, ry0 + patch_size)
                if _poly_intersects_rect(poly, rx0, ry0, rx1, ry1):
                    excluded_keys.add(_patch_key_from_xy(rx0, ry0))
    if excluded_keys:
        ops = [doc for doc in ops if doc.get("str_patch_key") not in excluded_keys]
        required_keys.difference_update(excluded_keys)

    excluded_patch_ids = []
    if excluded_keys:
        cursor = db.patch_annotation_status.find(
            {
                "str_slide_id": slide_id,
                "str_patch_key": {"$in": list(excluded_keys)},
            },
            {"str_patch_id": 1},
        )
        excluded_patch_ids = [
            str(doc.get("str_patch_id") or "")
            async for doc in cursor
            if doc.get("str_patch_id")
        ]
        await db.patch_annotation_status.delete_many({
            "str_slide_id": slide_id,
            "str_patch_key": {"$in": list(excluded_keys)},
        })
        if excluded_patch_ids:
            await db.patch_cell_annotations.delete_many({
                "str_slide_id": slide_id,
                "str_patch_id": {"$in": excluded_patch_ids},
            })
    added_count = 0
    now = _now()
    for doc in ops:
        existing_doc = await db.patch_annotation_status.find_one(
            {"str_slide_id": slide_id, "$or": [
                {"str_patch_key": doc["str_patch_key"]},
                {"str_patch_id": doc["str_patch_id"]},
            ]},
            {"_id": 1},
        )
        if existing_doc:
            continue
        await db.patch_annotation_status.update_one(
            {
                "str_slide_id": slide_id,
                "str_patch_key": doc["str_patch_key"],
            },
            {"$set": doc, "$setOnInsert": {"dt_created_at": now}},
            upsert=True,
        )
        added_count += 1
    _schedule_cell_annotation_export(slide_id)
    total_required = await db.patch_annotation_status.count_documents({
        "str_slide_id": slide_id,
        "str_status": {"$ne": "not_required"},
    })
    return {
        "status": "recomputed",
        "required_count": total_required,
        "added_count": added_count,
        "excluded_count": len(excluded_patch_ids),
    }


@router.get("/{slide_id}/patches")
async def get_patches(slide_id: str, status: str = Query("")):
    info = _slide_info(slide_id)
    db = _require_db()
    query: dict[str, Any] = {"str_slide_id": slide_id}
    if status:
        query["str_status"] = status
    else:
        query["str_status"] = {"$ne": "not_required"}
    projection = {
        "_id": 0,
        "str_slide_id": 1,
        "str_patch_id": 1,
        "str_patch_key": 1,
        "int_px": 1,
        "int_py": 1,
        "int_x": 1,
        "int_y": 1,
        "int_w": 1,
        "int_h": 1,
        "str_status": 1,
        "str_annotation_status": 1,
        "str_review_status": 1,
        "str_termination_status": 1,
        "str_memo": 1,
        "str_updated_by": 1,
        "dt_updated_at": 1,
    }
    cursor = db.patch_annotation_status.find(query, projection).sort([("int_py", 1), ("int_px", 1)])
    patches = await cursor.to_list(length=200000)
    for patch in patches:
        if not patch.get("str_patch_key"):
            patch["str_patch_key"] = _patch_key_from_xy(
                int(patch.get("int_x", 0)),
                int(patch.get("int_y", 0)),
            )
    return {"slide_id": slide_id, "patches": patches}


@router.delete("/{slide_id}/patches", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def clear_all_patches(slide_id: str):
    info = _slide_info(slide_id)
    db = _require_db()
    patch_count = await db.patch_annotation_status.count_documents({"str_slide_id": slide_id})
    cell_doc_count = await db.patch_cell_annotations.count_documents({"str_slide_id": slide_id})
    await db.patch_annotation_status.delete_many({"str_slide_id": slide_id})
    await db.patch_cell_annotations.delete_many({"str_slide_id": slide_id})
    await db.annotation_required_regions.delete_many({"str_slide_id": slide_id})
    _export_requested.discard(slide_id)
    task = _export_tasks.pop(slide_id, None)
    if task and not task.done():
        task.cancel()
    file_counts = _clear_cell_annotation_patch_files(slide_id, info)
    return {
        "status": "cleared",
        "slide_id": slide_id,
        "patch_count": patch_count,
        "cell_annotation_count": cell_doc_count,
        **file_counts,
    }


@router.get("/{slide_id}/wsi-labeling-assistance/options")
async def get_wsi_labeling_assistance_options(slide_id: str):
    info = _slide_info(slide_id)
    config = await _project_annotation_ai_config(info)
    return {
        "slide_id": slide_id,
        "project_path": _slide_project_path(info),
        "current": config,
        "options": ANNOTATION_AI_OPTIONS,
    }


@router.get("/{slide_id}/wsi-labeling-assistance")
async def get_wsi_labeling_assistance(
    slide_id: str,
    include_labels: bool = Query(False),
):
    info = _slide_info(slide_id)
    payload = _read_assistance_file(info)
    if not payload:
        return {"slide_id": slide_id, "exists": False, "labels": []}
    payload["exists"] = True
    if include_labels:
        return payload
    meta = _assistance_metadata(payload)
    meta["exists"] = True
    return meta


@router.post("/{slide_id}/wsi-labeling-assistance/run", dependencies=[Depends(require_not_viewer)])
async def start_wsi_labeling_assistance(
    slide_id: str,
    payload: Optional[dict] = Body(None),
):
    info = _slide_info(slide_id)
    config = await _project_annotation_ai_config(info)
    override_key = str((payload or {}).get("annotation_ai_key") or "").strip()
    if override_key:
        option = ANNOTATION_AI_OPTION_BY_KEY.get(override_key)
        if not option:
            raise HTTPException(400, f"Invalid annotation AI key: {override_key}")
        config = normalize_annotation_ai_config(True, override_key)
    if not config.get("enabled"):
        raise HTTPException(400, "Cell Annotation AI assistance is disabled for this project")
    task_id = uuid.uuid4().hex[:12]
    str_filename = Path(info.file_path).name
    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued",
            "progress": 0,
            "result": None,
            "error": None,
            "status_msg": "",
            "slide_filename": str_filename,
            "model": "WSI Labeling Assistance",
            "variant": config.get("label", ""),
        }
    ai_executor.submit(_run_labeling_assistance_task, task_id, slide_id, info.file_path, config)
    return {"task_id": task_id, "status": "queued", "annotation_ai": config}


@router.get("/wsi-labeling-assistance/task/{task_id}")
async def get_wsi_labeling_assistance_task(task_id: str):
    cleanup_old_tasks()
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    response = {
        "task_id": task_id,
        "status": task.get("status"),
        "progress": task.get("progress", 0),
        "status_msg": task.get("status_msg", ""),
    }
    if task.get("status") == "completed":
        response["result"] = task.get("result")
        release_task_result(task_id)
    elif task.get("status") == "error":
        response["error"] = task.get("error")
    return response


@router.get("/{slide_id}/patches/{patch_id}/assistance-cells")
async def get_patch_labeling_assistance_cells(slide_id: str, patch_id: str):
    info = _slide_info(slide_id)
    db = _require_db()
    patch = await db.patch_annotation_status.find_one(
        {"str_slide_id": slide_id, "str_patch_id": patch_id},
        {"_id": 0},
    )
    if not patch:
        raise HTTPException(404, "Patch not found")
    workflow_state = str(patch.get("str_annotation_status") or patch.get("str_status") or "")
    if workflow_state != "required":
        return {
            "slide_id": slide_id,
            "patch_id": patch_id,
            "exists": False,
            "reason": "patch_not_required",
            "cells": [],
        }
    payload = _read_assistance_file(info)
    labels = payload.get("labels") if isinstance(payload, dict) else None
    if not isinstance(labels, list):
        return {
            "slide_id": slide_id,
            "patch_id": patch_id,
            "exists": False,
            "reason": "assistance_missing",
            "cells": [],
        }
    class_lookup = _assistance_class_lookup(info, payload)
    cells = []
    for idx, label in enumerate(labels, start=1):
        cell = _assistance_label_to_cell(label, patch, idx, class_lookup)
        if cell is not None:
            cells.append(cell)
    return {
        "slide_id": slide_id,
        "patch_id": patch_id,
        "exists": True,
        "total_labels": len(labels),
        "cell_count": len(cells),
        "classes": _assistance_metadata(payload).get("classes") or _load_cell_classes_for_project(_slide_project_path(info)),
        "cells": cells,
    }


@router.get("/{slide_id}/patches/{patch_id}/cells")
async def get_patch_cells(slide_id: str, patch_id: str):
    _slide_info(slide_id)
    db = _require_db()
    doc = await db.patch_cell_annotations.find_one(
        {"str_slide_id": slide_id, "str_patch_id": patch_id},
        {"_id": 0},
    )
    return {"slide_id": slide_id, "patch_id": patch_id, "cells": (doc or {}).get("list_cells", [])}


@router.post("/{slide_id}/patches/{patch_id}/cells", dependencies=[Depends(require_not_viewer)])
async def save_patch_cells(
    slide_id: str,
    patch_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    info = _slide_info(slide_id)
    db = _require_db()
    patch = await db.patch_annotation_status.find_one({"str_slide_id": slide_id, "str_patch_id": patch_id})
    if not patch:
        raise HTTPException(404, "Patch not found")
    if user.get("str_role") == UserRole.LABELER.value:
        review_state = str(patch.get("str_review_status") or "pending")
        termination_state = str(patch.get("str_termination_status") or "pending")
        if review_state not in ("", "pending") or termination_state not in ("", "pending"):
            raise HTTPException(403, "Patch annotations are locked after review or termination starts")
    raw_cells = payload.get("cells", [])
    if not isinstance(raw_cells, list):
        raise HTTPException(400, "cells must be a list")
    cells = [_normalize_cell(cell, patch) for cell in raw_cells if isinstance(cell, dict)]
    complete = bool(payload.get("complete"))
    now = _now()
    await db.patch_cell_annotations.update_one(
        {"str_slide_id": slide_id, "str_patch_id": patch_id},
        {"$set": {
            "str_slide_id": slide_id,
            "str_patch_id": patch_id,
            "list_cells": cells,
            "str_updated_by": str(user.get("_id", "")),
            "dt_updated_at": now,
        }, "$setOnInsert": {"dt_created_at": now}},
        upsert=True,
    )
    patch_update = {
        "dt_updated_at": now,
        "str_updated_by": str(user.get("_id", "")),
    }
    should_reload_patch = False
    if complete:
        patch_update.update({
            "str_status": "completed",
            **_patch_workflow_fields("completed"),
        })
        await db.patch_annotation_status.update_one(
            {"str_slide_id": slide_id, "str_patch_id": patch_id},
            {"$set": patch_update},
        )
        should_reload_patch = True
    else:
        draft_status = str(payload.get("annotation_status") or payload.get("status") or "").strip()
        if payload.get("preserve_status") and draft_status in {"required", "in_progress"}:
            patch_update.update({
                "str_status": draft_status,
                **_patch_workflow_fields(draft_status),
            })
            await db.patch_annotation_status.update_one(
                {"str_slide_id": slide_id, "str_patch_id": patch_id},
                {"$set": patch_update},
            )
            should_reload_patch = True
    _schedule_cell_annotation_export(slide_id)
    updated_patch = None
    if should_reload_patch:
        updated_patch = await db.patch_annotation_status.find_one(
            {"str_slide_id": slide_id, "str_patch_id": patch_id},
            {"_id": 0},
        )
    return {
        "status": "saved",
        "patch_status": (updated_patch or patch or {}).get("str_status", "required"),
        "cell_count": len(cells),
        "patch": updated_patch or {**(patch or {}), "str_slide_id": slide_id, "str_patch_id": patch_id},
    }


@router.put("/{slide_id}/patches/{patch_id}/status", dependencies=[Depends(require_not_viewer)])
async def update_patch_status(
    slide_id: str,
    patch_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
):
    info = _slide_info(slide_id)
    db = _require_db()
    status = str(payload.get("status", "")).strip()
    if status not in PATCH_STATUSES:
        raise HTTPException(400, f"Invalid patch status: {status}")
    existing = await db.patch_annotation_status.find_one({"str_slide_id": slide_id, "str_patch_id": patch_id})
    bool_labeler = user.get("str_role") == UserRole.LABELER.value
    if bool_labeler:
        if status == "not_required" or payload.get("manual_excluded") or payload.get("excluded"):
            raise HTTPException(403, "Labeler role cannot remove required patches")
        if "memo" in payload or "memo_history" in payload:
            raise HTTPException(403, "Labeler role cannot change patch memo")
        if "review_status" in payload or "termination_status" in payload:
            raise HTTPException(403, "Labeler role cannot change review or termination status")
        review_state = str((existing or {}).get("str_review_status") or "pending")
        termination_state = str((existing or {}).get("str_termination_status") or "pending")
        if review_state not in ("", "pending") or termination_state not in ("", "pending"):
            raise HTTPException(403, "Annotation status is locked after review or termination starts")
        annotation_state = str(payload.get("annotation_status") or status).strip()
        if annotation_state not in {"required", "in_progress", "completed"}:
            raise HTTPException(403, "Labeler role can only change annotation status")
    if status == "not_required":
        if not existing:
            raise HTTPException(404, "Patch not found")
        await db.patch_annotation_status.delete_one({"str_slide_id": slide_id, "str_patch_id": patch_id})
        await db.patch_cell_annotations.delete_one({"str_slide_id": slide_id, "str_patch_id": patch_id})
        _schedule_cell_annotation_export(slide_id)
        return {"status": "removed", "patch_id": patch_id}
    if existing:
        px = int(existing.get("int_px", 0))
        py = int(existing.get("int_py", 0))
    else:
        parts = patch_id.replace("px_", "").replace("py_", "").split("_")
        try:
            patch_size = _patch_slide_size(info)
            x = int(parts[0])
            y = int(parts[1])
            px = max(0, int(round(x / patch_size)))
            py = max(0, int(round(y / patch_size)))
        except Exception:
            raise HTTPException(404, "Patch not found")
    doc = _patch_doc(slide_id, px, py, status, info, user)
    doc["str_patch_id"] = existing.get("str_patch_id") if existing else patch_id
    doc["str_patch_key"] = existing.get("str_patch_key") if existing else _patch_key_from_xy(doc["int_x"], doc["int_y"])
    doc["bool_manual_excluded"] = bool(payload.get("manual_excluded") or payload.get("excluded")) and status == "not_required"
    for key in ("annotation_status", "review_status", "termination_status"):
        if key in payload:
            field = f"str_{key}"
            doc[field] = str(payload.get(key) or "").strip()[:80]
    if "memo" in payload:
        doc["str_memo"] = str(payload.get("memo") or "").strip()[:2000]
    if "memo_history" in payload:
        doc["list_memo_history"] = _normalize_memo_history(payload.get("memo_history"))
    if bool_labeler:
        doc["str_review_status"] = str((existing or {}).get("str_review_status") or "pending")
        doc["str_termination_status"] = str((existing or {}).get("str_termination_status") or "pending")
    now = _now()
    await db.patch_annotation_status.update_one(
        {"str_slide_id": slide_id, "str_patch_id": patch_id},
        {"$set": doc, "$setOnInsert": {"dt_created_at": now}},
        upsert=True,
    )
    _schedule_cell_annotation_export(slide_id)
    return {"status": "saved", "patch": doc}
