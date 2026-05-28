"""Patch-based cell annotation workflow endpoints."""

from datetime import datetime, timezone
import json
from math import ceil, floor
from pathlib import Path
import re
import threading
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request

from app.auth import get_current_user, require_not_viewer, require_role
from app.database import get_db, is_db_connected
from app.models import UserRole
from app.path_utils import safe_filename, safe_subpath
from app.project_utils import ANNOTATION_AI_OPTION_BY_KEY, ANNOTATION_AI_OPTIONS, normalize_annotation_ai_config
from app.slide_manager import slide_manager
from app.ai_pipelines.detection import run_detection as _run_detection
from app.ai_pipelines.marker_pipeline import (
    run_pd_score as _run_pd_score,
    run_precise_ihc as _run_precise_ihc,
)
from app.ai_pipelines.task_state import _tasks, _tasks_lock, cleanup_old_tasks, release_task_result, update_task
from app.config import settings


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
DEFAULT_CELL_CLASSES = [
    {"id": "cell", "name": "Cell", "color": [0, 255, 0]},
]


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


def _patch_key_from_xy(x: int, y: int) -> str:
    return f"px_{int(x)}_py_{int(y)}"


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


def _region_points(region: dict) -> list[list[float]]:
    points = region.get("points") or region.get("coordinates") or []
    out = []
    for pt in points:
        if isinstance(pt, dict):
            x = pt.get("x")
            y = pt.get("y")
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            x, y = pt[0], pt[1]
        else:
            continue
        try:
            out.append([float(x), float(y)])
        except Exception:
            continue
    return out


def _bbox(points: list[list[float]]) -> Optional[tuple[float, float, float, float]]:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_poly(x: float, y: float, poly: list[list[float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


def _segments_intersect(a, b, c, d) -> bool:
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_seg(p, q, r):
        return (
            min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
            and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
        )

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    eps = 1e-9
    return (
        abs(o1) < eps and on_seg(a, c, b)
        or abs(o2) < eps and on_seg(a, d, b)
        or abs(o3) < eps and on_seg(c, a, d)
        or abs(o4) < eps and on_seg(c, b, d)
    )


def _poly_intersects_rect(poly: list[list[float]], x0: float, y0: float, x1: float, y1: float) -> bool:
    if len(poly) < 3:
        return False
    poly_box = _bbox(poly)
    if not poly_box:
        return False
    bx0, by0, bx1, by1 = poly_box
    if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
        return False
    rect = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    if any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in poly):
        return True
    if any(_point_in_poly(x, y, poly) for x, y in rect):
        return True
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        for j in range(4):
            if _segments_intersect(a, b, rect[j], rect[(j + 1) % 4]):
                return True
    return False


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
    return {
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


def _write_patch_image(info, patch: dict, out_path: Path) -> None:
    if out_path.exists():
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import openslide

        slide = openslide.OpenSlide(info.file_path)
        try:
            x = int(patch.get("int_x", 0))
            y = int(patch.get("int_y", 0))
            w = max(1, int(patch.get("int_w", 0)))
            h = max(1, int(patch.get("int_h", 0)))
            image = slide.read_region((x, y), 0, (w, h)).convert("RGB")
            image.save(out_path, "JPEG", quality=90, optimize=True)
        finally:
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
        _write_patch_image(info, patch, patches_dir / f"{patch_id}.jpeg")
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

    _write_json(root / "info.json", {
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
    })
    (root / "WSI_regions.json").unlink(missing_ok=True)


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
    already_compact = payload.get("label_format") == "bbox_compact_v1" and (
        not labels or isinstance(labels[0], list)
    )
    if already_compact:
        payload["total_labels"] = len(labels)
        payload["total_model_bbox_labels"] = int(payload.get("total_model_bbox_labels") or len(labels))
        return payload, False
    compact_labels = []
    for label in labels:
        compact = _compact_assistance_label(label)
        if compact is not None:
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
    inherit_classes = bool(config.get("inherit_classes"))
    labels = []
    used_model_bbox = False
    for idx, cell in enumerate((result or {}).get("cells") or [], start=1):
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
        labels.append({
            "id": f"assist_{idx}",
            "x": round(x0, 2),
            "y": round(y0, 2),
            "width": round(max(0.0, x1 - x0), 2),
            "height": round(max(0.0, y1 - y0), 2),
            "center_x": round(x, 2),
            "center_y": round(y, 2),
            "class_id": str_class_id if inherit_classes else "",
            "class_name": str(class_names.get(str_class_id, "")) if inherit_classes else "",
            "confidence": round(confidence, 4),
            "source_format": "bbox",
            "bbox_source": "model" if bbox is not None else "fallback_point",
        })
    return labels, used_model_bbox


def _write_assistance_result(slide_id: str, info, config: dict, result: dict) -> dict:
    labels, used_model_bbox = _result_cells_to_bbox_labels(result, config)
    if labels and not used_model_bbox:
        raise ValueError(
            "Labeling assistance requires model bbox output, but the AI result only contains points. "
            "Remove the stale AI result cache and rerun annotation assistance."
        )
    compact_labels = [_compact_assistance_label(label) for label in labels]
    compact_labels = [label for label in compact_labels if label is not None]
    payload = {
        "slide_id": slide_id,
        "slide_filename": Path(info.file_path).name,
        "slide_stem": Path(info.file_path).stem,
        "generated_at": _now().isoformat(),
        "annotation_ai": config,
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
    if not class_path.exists():
        return {"classes": list(DEFAULT_CELL_CLASSES)}
    try:
        payload = json.loads(class_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"Invalid cell annotation class JSON: {exc}")
    classes = payload.get("classes") if isinstance(payload, dict) else payload
    return {"classes": _normalize_cell_classes(classes)}


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
    skipped_keys = set()
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

    now = _now()
    stale_query: dict[str, Any] = {"str_slide_id": slide_id}
    keep_keys = list(required_keys)
    if keep_keys:
        stale_query["str_patch_key"] = {"$nin": keep_keys}
    await db.patch_annotation_status.delete_many(stale_query)
    if excluded_keys:
        await db.patch_annotation_status.delete_many({
            "str_slide_id": slide_id,
            "str_patch_key": {"$in": list(excluded_keys)},
        })
    for doc in ops:
        existing_doc = await db.patch_annotation_status.find_one(
            {"str_slide_id": slide_id, "$or": [
                {"str_patch_key": doc["str_patch_key"]},
                {"str_patch_id": doc["str_patch_id"]},
            ]},
            {"_id": 1},
        )
        update_filter = {"_id": existing_doc["_id"]} if existing_doc else {
            "str_slide_id": slide_id,
            "str_patch_key": doc["str_patch_key"],
        }
        await db.patch_annotation_status.update_one(
            update_filter,
            {"$set": doc, "$setOnInsert": {"dt_created_at": now}},
            upsert=True,
        )
    await _export_cell_annotation_files(slide_id, info, regions)
    return {"status": "recomputed", "required_count": len(required_keys), "excluded_count": len(excluded_keys)}


@router.get("/{slide_id}/patches")
async def get_patches(slide_id: str, status: str = Query("")):
    info = _slide_info(slide_id)
    db = _require_db()
    await db.patch_annotation_status.delete_many({"str_slide_id": slide_id, "str_status": "not_required"})
    query: dict[str, Any] = {"str_slide_id": slide_id}
    if status:
        query["str_status"] = status
    else:
        query["str_status"] = {"$ne": "not_required"}
    cursor = db.patch_annotation_status.find(query, {"_id": 0}).sort([("int_py", 1), ("int_px", 1)])
    patches = await cursor.to_list(length=200000)
    allocated_ids: dict[str, str] = {}
    for patch in patches:
        old_id = patch.get("str_patch_id")
        patch_key = patch.get("str_patch_key") or _patch_key_from_xy(int(patch.get("int_x", 0)), int(patch.get("int_y", 0)))
        expected_id = await _patch_id_for_key(db, slide_id, patch_key, allocated_ids)
        if old_id and expected_id and old_id != expected_id:
            patch["str_patch_id"] = expected_id
            patch["str_patch_key"] = patch_key
            await db.patch_annotation_status.update_one(
                {"str_slide_id": slide_id, "str_patch_id": old_id},
                {"$set": {"str_patch_id": expected_id, "str_patch_key": patch_key}},
            )
            await db.patch_cell_annotations.update_many(
                {"str_slide_id": slide_id, "str_patch_id": old_id},
                {"$set": {"str_patch_id": expected_id}},
            )
        elif patch_key and not patch.get("str_patch_key"):
            patch["str_patch_key"] = patch_key
            await db.patch_annotation_status.update_one(
                {"str_slide_id": slide_id, "str_patch_id": old_id},
                {"$set": {"str_patch_key": patch_key}},
            )
    return {"slide_id": slide_id, "patches": patches}


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
        raise HTTPException(400, "Annotation AI assistance is disabled for this project")
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
    thread = threading.Thread(
        target=_run_labeling_assistance_task,
        args=(task_id, slide_id, info.file_path, config),
        daemon=True,
    )
    thread.start()
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
    await db.patch_annotation_status.update_one(
        {"str_slide_id": slide_id, "str_patch_id": patch_id},
        {"$set": {
            "str_status": "completed",
            **_patch_workflow_fields("completed"),
            "dt_updated_at": now,
            "str_updated_by": str(user.get("_id", "")),
        }},
    )
    region_doc = await db.annotation_required_regions.find_one({"str_slide_id": slide_id}, {"_id": 0})
    await _export_cell_annotation_files(slide_id, info, (region_doc or {}).get("list_regions", []))
    return {"status": "saved", "patch_status": "completed", "cell_count": len(cells)}


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
        region_doc = await db.annotation_required_regions.find_one({"str_slide_id": slide_id}, {"_id": 0})
        await _export_cell_annotation_files(slide_id, info, (region_doc or {}).get("list_regions", []))
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
    region_doc = await db.annotation_required_regions.find_one({"str_slide_id": slide_id}, {"_id": 0})
    await _export_cell_annotation_files(slide_id, info, (region_doc or {}).get("list_regions", []))
    return {"status": "saved", "patch": doc}
