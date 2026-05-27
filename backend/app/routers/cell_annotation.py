"""Patch-based cell annotation workflow endpoints."""

from datetime import datetime, timezone
from math import ceil, floor
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.auth import get_current_user, require_not_viewer, require_role
from app.database import get_db, is_db_connected
from app.models import UserRole
from app.slide_manager import slide_manager


router = APIRouter(dependencies=[Depends(get_current_user)])

TARGET_MPP = 0.5
PATCH_PHYSICAL_UM = 512.0
TARGET_PATCH_SIZE = int(round(PATCH_PHYSICAL_UM / TARGET_MPP))
PATCH_STATUSES = {
    "not_required",
    "required",
    "in_progress",
    "completed",
    "reviewed",
    "rejected",
}


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


def _patch_id_from_xy(x: int, y: int) -> str:
    return f"px_{int(x)}_py_{int(y)}"


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


def _patch_doc(slide_id: str, px: int, py: int, status: str, info, user: dict) -> dict:
    patch_size = _patch_slide_size(info)
    x0 = px * patch_size
    y0 = py * patch_size
    w, h = info.dimensions
    return {
        "str_slide_id": slide_id,
        "str_patch_id": _patch_id_from_xy(x0, y0),
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
    return {
        "str_region_id": str(item.get("id") or item.get("region_id") or f"region_{idx}"),
        "str_type": "annotation_required_region",
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
    _slide_info(slide_id)
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
    return {"status": "saved", "count": len(regions), "regions": regions}


@router.get("/{slide_id}/required-regions")
async def get_required_regions(slide_id: str):
    _slide_info(slide_id)
    db = _require_db()
    doc = await db.annotation_required_regions.find_one({"str_slide_id": slide_id}, {"_id": 0})
    return {"slide_id": slide_id, "regions": (doc or {}).get("list_regions", [])}


@router.post("/{slide_id}/patches/recompute-status", dependencies=[Depends(require_not_viewer)])
async def recompute_patch_status(slide_id: str, user: dict = Depends(get_current_user)):
    info = _slide_info(slide_id)
    db = _require_db()
    region_doc = await db.annotation_required_regions.find_one({"str_slide_id": slide_id}, {"_id": 0})
    regions = (region_doc or {}).get("list_regions", [])
    patch_size = _patch_slide_size(info)
    width, height = info.dimensions
    ops = []
    required_ids = set()
    skipped_ids = set()
    for region in regions:
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
                pid = _patch_id_from_xy(rx0, ry0)
                if pid in required_ids or pid in skipped_ids:
                    continue
                existing = await db.patch_annotation_status.find_one(
                    {"str_slide_id": slide_id, "str_patch_id": pid},
                    {"str_status": 1, "bool_manual_excluded": 1},
                )
                if (existing or {}).get("bool_manual_excluded"):
                    skipped_ids.add(pid)
                    continue
                required_ids.add(pid)
                status = (existing or {}).get("str_status") or "required"
                if status == "not_required":
                    status = "required"
                ops.append(_patch_doc(slide_id, px, py, status, info, user))

    now = _now()
    await db.patch_annotation_status.update_many(
        {"str_slide_id": slide_id, "str_status": {"$in": ["required", "in_progress"]}},
        {"$set": {
            "str_status": "not_required",
            **_patch_workflow_fields("not_required"),
            "dt_updated_at": now,
        }},
    )
    for doc in ops:
        await db.patch_annotation_status.update_one(
            {"str_slide_id": slide_id, "str_patch_id": doc["str_patch_id"]},
            {"$set": doc, "$setOnInsert": {"dt_created_at": now}},
            upsert=True,
        )
    return {"status": "recomputed", "required_count": len(required_ids)}


@router.get("/{slide_id}/patches")
async def get_patches(slide_id: str, status: str = Query("")):
    _slide_info(slide_id)
    db = _require_db()
    query: dict[str, Any] = {"str_slide_id": slide_id}
    if status:
        query["str_status"] = status
    cursor = db.patch_annotation_status.find(query, {"_id": 0}).sort([("int_py", 1), ("int_px", 1)])
    patches = await cursor.to_list(length=200000)
    for patch in patches:
        old_id = patch.get("str_patch_id")
        expected_id = _patch_id_from_xy(int(patch.get("int_x", 0)), int(patch.get("int_y", 0)))
        if old_id and expected_id and old_id != expected_id:
            patch["str_patch_id"] = expected_id
            await db.patch_annotation_status.update_one(
                {"str_slide_id": slide_id, "str_patch_id": old_id},
                {"$set": {"str_patch_id": expected_id}},
            )
            await db.patch_cell_annotations.update_many(
                {"str_slide_id": slide_id, "str_patch_id": old_id},
                {"$set": {"str_patch_id": expected_id}},
            )
    return {"slide_id": slide_id, "patches": patches}


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
    _slide_info(slide_id)
    db = _require_db()
    patch = await db.patch_annotation_status.find_one({"str_slide_id": slide_id, "str_patch_id": patch_id})
    if not patch:
        raise HTTPException(404, "Patch not found")
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
    doc["bool_manual_excluded"] = bool(payload.get("manual_excluded") or payload.get("excluded")) and status == "not_required"
    if "memo" in payload:
        doc["str_memo"] = str(payload.get("memo") or "").strip()[:2000]
    if "memo_history" in payload:
        doc["list_memo_history"] = _normalize_memo_history(payload.get("memo_history"))
    now = _now()
    await db.patch_annotation_status.update_one(
        {"str_slide_id": slide_id, "str_patch_id": patch_id},
        {"$set": doc, "$setOnInsert": {"dt_created_at": now}},
        upsert=True,
    )
    return {"status": "saved", "patch": doc}
