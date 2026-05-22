"""Annotation class and annotation JSON storage endpoints."""

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request

from app import tile_generator
from app.auth import get_current_user, require_not_viewer, require_role
from app.config import settings
from app.models import UserRole
from app.path_utils import safe_filename, safe_subpath
from app.slide_manager import slide_manager


router = APIRouter()

_INT_ANNOTATIONS_MAX_BYTES = 8 * 1024 * 1024
_INT_ANNOTATION_CLASSES_MAX_BYTES = 256 * 1024
_DEFAULT_ANNOTATION_CLASSES = [
    {"id": "default", "name": "Default", "color": [0, 255, 0]},
]


def _annotation_slide_dirname(filename: str) -> str:
    str_name = Path(filename).name.strip() or "slide"
    for ch in '<>:"/\\|?*':
        str_name = str_name.replace(ch, "_")
    str_name = "".join("_" if ord(ch) < 32 else ch for ch in str_name)
    str_name = str_name.rstrip(" .")
    if str_name in {"", ".", ".."}:
        str_name = hashlib.sha256(filename.encode("utf-8", "ignore")).hexdigest()[:16]
    return str_name


def _annotation_path_for_filename(filename: str) -> Path:
    return Path(settings.ANNOTATIONS_DIR) / _annotation_slide_dirname(filename) / "annotations.json"


def _annotation_classes_path_for_project(project_path: str) -> Path:
    str_project = (project_path or "").replace("\\", "/").split("/")[0].strip()
    if not str_project:
        raise HTTPException(400, "Project path is required")
    str_project = safe_filename(str_project)
    project_dir = safe_subpath(str_project)
    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(404, "Project not found")
    return Path(settings.ANNOTATIONS_DIR) / "_projects" / _annotation_slide_dirname(str_project) / "classes.json"


def _normalize_annotation_color(value) -> list[int]:
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


def _normalize_annotation_classes(value) -> list[dict]:
    if not isinstance(value, list):
        raise HTTPException(400, "annotation classes must be a list")
    list_classes = []
    set_seen = set()
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:64] or f"Class {idx}"
        raw_id = str(item.get("id") or name).strip()[:80]
        raw_id = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in raw_id)
        raw_id = raw_id.strip("_-") or hashlib.sha256(name.encode("utf-8", "ignore")).hexdigest()[:10]
        base_id = raw_id
        suffix = 2
        while raw_id in set_seen:
            raw_id = f"{base_id}_{suffix}"
            suffix += 1
        set_seen.add(raw_id)
        list_classes.append({
            "id": raw_id,
            "name": name,
            "color": _normalize_annotation_color(item.get("color")),
        })
    return list_classes or list(_DEFAULT_ANNOTATION_CLASSES)


@router.get("/annotation-classes")
async def load_annotation_classes(path: str = Query(..., description="project path or current folder path")):
    class_path = _annotation_classes_path_for_project(path)
    if not class_path.exists():
        return {"classes": list(_DEFAULT_ANNOTATION_CLASSES)}
    with open(class_path, "r", encoding="utf-8") as file_obj:
        try:
            payload = json.loads(file_obj.read())
        except Exception as exc:
            raise HTTPException(400, f"Invalid annotation class JSON: {exc}")
    classes = payload.get("classes") if isinstance(payload, dict) else payload
    return {"classes": _normalize_annotation_classes(classes)}


@router.post("/annotation-classes", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def save_annotation_classes(
    request: Request,
    path: str = Form(...),
    data: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    if len(data.encode("utf-8")) > _INT_ANNOTATION_CLASSES_MAX_BYTES:
        raise HTTPException(413, "annotation class data is too large")
    try:
        payload = json.loads(data)
    except Exception as exc:
        raise HTTPException(400, f"Invalid annotation class JSON: {exc}")
    classes = _normalize_annotation_classes(payload.get("classes") if isinstance(payload, dict) else payload)
    class_path = _annotation_classes_path_for_project(path)
    class_path.parent.mkdir(parents=True, exist_ok=True)
    with open(class_path, "w", encoding="utf-8") as file_obj:
        json.dump({"classes": classes}, file_obj, ensure_ascii=False, indent=2)

    from app.routers.slides import _log_management_event

    str_project_id = (path or "").replace("\\", "/").split("/")[0]
    await _log_management_event(
        request,
        dict_user,
        str_action="annotation_classes.update",
        str_resource_type="project",
        str_resource_id=str_project_id,
        str_detail=f"Updated annotation classes for {str_project_id}",
        dict_after={"classes": classes},
    )
    return {"status": "saved", "count": len(classes), "classes": classes}


@router.post("/{slide_id}/annotations/save", dependencies=[Depends(require_not_viewer)])
async def save_annotations(slide_id: str, data: str = Form(...)):
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Slide not found")

    if len(data.encode("utf-8")) > _INT_ANNOTATIONS_MAX_BYTES:
        raise HTTPException(413, f"annotation data is too large ({_INT_ANNOTATIONS_MAX_BYTES // (1024 * 1024)} MB)")
    try:
        parsed = json.loads(data)
    except Exception as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}")
    if isinstance(parsed, list):
        list_parsed = parsed
        payload_to_save = parsed
    elif isinstance(parsed, dict) and isinstance(parsed.get("annotations"), list):
        list_parsed = parsed.get("annotations") or []
        payload_to_save = {
            "slide_memo": str(parsed.get("slide_memo") or parsed.get("memo") or "")[:10000],
            "slide_memo_history": parsed.get("slide_memo_history") or parsed.get("memo_history") or [],
            "annotations": list_parsed,
        }
    else:
        raise HTTPException(400, "annotation data must be a list or an object with annotations")

    filename = Path(info.file_path).name
    ann_path = _annotation_path_for_filename(filename)
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ann_path, "w", encoding="utf-8") as file_obj:
        json.dump(payload_to_save, file_obj, ensure_ascii=False, indent=2)
    return {"status": "saved", "count": len(list_parsed), "path": str(ann_path)}


@router.get("/{slide_id}/annotations/load")
async def load_annotations(slide_id: str):
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Slide not found")
    filename = Path(info.file_path).name
    ann_path = _annotation_path_for_filename(filename)
    if not ann_path.exists():
        ann_path = tile_generator.get_tiles_dir(filename) / "annotations.json"
    if not ann_path.exists():
        return []
    with open(ann_path, "r", encoding="utf-8") as file_obj:
        return json.loads(file_obj.read())
