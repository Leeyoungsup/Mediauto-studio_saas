"""
?????? ???API ???????(???), ??? ??? ???, ???, ???, ???
???????????????????+ ??? ??? ???
"""

import os
import json
import uuid
import asyncio
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.audit import get_client_ip, log_audit_event
from app.activity_audit import audit_activity
from app.auth import get_current_user, require_not_viewer, require_role
from app.config import settings
from app.clinical_info import (
    case_filename_regex as _case_filename_regex,
    case_name_from_filename as _case_name_from_filename,
    get_case_clinical_info as _get_case_clinical_info,
    has_clinical_info as _has_clinical_info,
    iso_datetime as _iso_datetime,
    normalize_clinical_info as _normalize_clinical_info,
    upsert_case_clinical_info as _upsert_case_clinical_info,
)
from app.models import UserRole
from app.repositories.operational_store import get_clinical_info_store
from app.path_utils import (
    rel_path_for as _rel_path_for,
    safe_filename as _safe_filename,
    safe_subpath as _safe_subpath,
)
from app.slide_identity import slide_cache_key
from app.jpeg_to_pyramidal_tiff import (
    convert_jpeg_to_pyramidal_tiff,
    converted_tiff_filename,
    converted_tiff_path,
)
from app.dicom_slide import cleanup_dicom_archive_cache
from app.project_utils import (
    clean_ai_tasks as _clean_ai_tasks,
    list_project_dirs as _list_project_dirs,
    parse_ai_tasks_json as _parse_ai_tasks_json,
    project_public_info as _project_public_info,
    upsert_project_info as _upsert_project_info,
)
from app.slide_manager import slide_manager
from app import tile_generator
from app import slide_store
from app import auto_ai
from app.cpu_layout import bg_executor, upload_executor, viewer_executor

router = APIRouter(dependencies=[Depends(get_current_user)])

# ??????????????? ??? ??? ???????Bearer JWT ??? ?mt= ??? ???.
# ???router ? ??? prefix("/api/slides") ??main.py ??? ??? include ???.


def _hash_file(path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            bytes_block = f.read(1024 * 1024)
            if not bytes_block:
                break
            sha256_hash.update(bytes_block)
    return sha256_hash.hexdigest()


def _join_upload_chunks(chunk_dir: Path, final_path: Path, total_chunks: int) -> str:
    sha256_hash = hashlib.sha256()
    with open(final_path, "wb") as out:
        for i in range(total_chunks):
            chunk_path = chunk_dir / f"chunk_{i:06d}"
            with open(chunk_path, "rb") as cf:
                while True:
                    bytes_block = cf.read(1024 * 1024)
                    if not bytes_block:
                        break
                    out.write(bytes_block)
                    sha256_hash.update(bytes_block)
    return sha256_hash.hexdigest()


def _slide_response(slide_id: str, info, filename: str):
    """?????? ??? ??? ??? ???"""
    return {
        "slide_id": slide_id,
        "filename": filename,
        "dimensions": info.dimensions,
        "level_count": info.level_count,
        "level_dimensions": info.level_dimensions,
        "level_downsamples": info.level_downsamples,
        # 3??? stage ?????? (??????/??? ???)
        "stage_count": info.stage_count,
        "stage_downsamples": info.stage_downsamples,
        "stage_dimensions": info.stage_dimensions,
        "mpp": info.mpp,
        "mpp_x": info.mpp_x,
        "mpp_y": info.mpp_y,
        "vendor": info.vendor,
        "objective_power": info.objective_power,
        "physical_width_mm": info.physical_width_mm,
        "physical_height_mm": info.physical_height_mm,
        "tiles_ready": tile_generator.tiles_marker_matches_file(filename, info.file_path),
    }


async def _open_and_generate(
    slide_id: str,
    file_path: str,
    filename: str,
    dict_user: Optional[dict] = None,
    bool_wait_for_tiles: bool = False,
    str_sha256: str = "",
    str_last_opened_page: str = "ai",
):
    """?????? ??? + ?????? ??DB ?????????? ???.

    `bool_wait_for_tiles=True` ????????????? ?????????? ?????????
    ??? ???? ?????????????????? ???/??? ?????? on-demand ???
    ???????? ??????????????????? ???.
    """
    # ??? ?????????????
    existing = slide_manager.get(slide_id)
    if existing:
        await _run_tile_gen(filename, file_path, bool_wait_for_tiles)
        resp = _slide_response(slide_id, existing, filename)
        await _upsert_and_attach(resp, slide_id, file_path, filename, existing, dict_user, str_sha256, str_last_opened_page)
        return resp

    try:
        # DICOM/Philips initialization performs blocking metadata and index
        # reads. Keep it off the ASGI event loop so health/auth/other slide
        # requests remain responsive while a slide is opening.
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(
            viewer_executor,
            slide_manager.open,
            slide_id,
            file_path,
        )
    except Exception as e:
        raise HTTPException(400, f"?????? ??? ???: {e}")

    await _run_tile_gen(filename, file_path, bool_wait_for_tiles)
    resp = _slide_response(slide_id, info, filename)
    await _upsert_and_attach(resp, slide_id, file_path, filename, info, dict_user, str_sha256, str_last_opened_page)
    return resp


async def _run_tile_gen(filename: str, file_path: str, bool_wait: bool) -> None:
    """?????? ???. wait ??????????? ??? (bg_executor), ??????????????????"""
    if tile_generator.tiles_marker_matches_file(filename, file_path):
        return
    if not bool_wait:
        tile_generator.start_generation(filename, file_path)
        return
    # ??? ??? ??bg_executor ????? ?????????????????
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        bg_executor, tile_generator._generate_tiles, filename, file_path
    )
    # mark_tiles_ready ??_generate_tiles ? threadsafe ??????????
    # ???????? ??? DB ? ???????????????????????? ???.
    try:
        str_rel = _rel_path_for(file_path)
        await slide_store.mark_tiles_ready(str_rel, filename, True)
    except Exception as e:
        print(f"[slides] mark_tiles_ready post-upload failed ({filename}): {e}")


async def _upsert_and_attach(
    resp: dict,
    slide_id: str,
    file_path: str,
    filename: str,
    info,
    dict_user: Optional[dict],
    str_sha256: str = "",
    str_last_opened_page: str = "ai",
):
    """slides ?????? upsert + ?????ai_results ????????(DB ?????no-op)."""
    try:
        int_size_bytes = os.path.getsize(file_path)
    except Exception:
        int_size_bytes = 0

    str_uploaded_by = ""
    if dict_user:
        str_uploaded_by = str(dict_user.get("_id") or "")

    dict_doc = await slide_store.upsert_slide(
        str_slide_id=slide_id,
        str_filename=filename,
        str_rel_path=_rel_path_for(file_path),
        str_full_path=file_path,
        dict_info=resp,
        int_size_bytes=int_size_bytes,
        str_uploaded_by=str_uploaded_by,
        str_last_opened_page=str_last_opened_page,
    )
    if dict_doc:
        resp["ai_results"] = slide_store.serialize_slide_doc(dict_doc).get("dict_ai_results")
        dt_up = dict_doc.get("dt_uploaded_at")
        resp["uploaded_at"] = dt_up.replace(tzinfo=timezone.utc).isoformat() if dt_up and not dt_up.tzinfo else (dt_up.isoformat() if dt_up else None)
        # SHA-256 ????????
        if str_sha256 and not dict_doc.get("str_sha256"):
            from app.database import get_db as _get_db
            db = _get_db()
            await db.slides.update_one(
                {"str_slide_id": slide_id, "str_filename": filename},
                {"$set": {"str_sha256": str_sha256}},
            )
        resp["sha256"] = str_sha256 or dict_doc.get("str_sha256", "")


async def _log_management_event(
    request: Request,
    dict_user: dict,
    *,
    str_action: str,
    str_resource_type: str,
    str_resource_id: str,
    str_detail: str,
    dict_extra: Optional[dict] = None,
    dict_before: Optional[dict] = None,
    dict_after: Optional[dict] = None,
) -> None:
    """Best-effort audit log for project/file management actions."""
    try:
        await log_audit_event(
            str_action=str_action,
            str_user_id=str(dict_user.get("_id", "")),
            str_user_email=dict_user.get("str_login_id", ""),
            str_resource_type=str_resource_type,
            str_resource_id=str_resource_id,
            str_detail=str_detail,
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
            dict_extra=dict_extra or {},
            dict_before=dict_before,
            dict_after=dict_after,
        )
    except Exception as e:
        print(f"[audit] management log failed ({str_action}): {e}")


@router.get("/dashboard")
async def dashboard(include_storage: bool = Query(False)):
    """???????? ??? ?????? + AI/??? ???."""
    list_recent = await slide_store.get_recent_slides(12)
    dict_stats = await slide_store.get_dashboard_stats(bool_include_disk=include_storage)

    list_recent_out = []
    for dict_doc in list_recent:
        dt_opened = dict_doc.get("dt_last_opened_at")
        dict_ai = dict_doc.get("dict_ai_results") or slide_store._empty_ai_results()
        # AI ??? ??? ????????
        list_ai_done = [
            str_k for str_k, v in dict_ai.items()
            if v.get("bool_has_result")
        ]
        str_full_path = dict_doc.get("str_full_path") or ""
        list_recent_out.append({
            "slide_id": slide_cache_key(str_full_path) if str_full_path else dict_doc.get("str_slide_id", ""),
            "filename": dict_doc.get("str_filename", ""),
            "rel_path": dict_doc.get("str_rel_path", ""),
            "size_bytes": dict_doc.get("int_size_bytes", 0),
            "mpp": dict_doc.get("float_mpp"),
            "status": dict_doc.get("str_status", ""),
            "last_opened_page": dict_doc.get("str_last_opened_page") or "",
            "last_opened_at": dt_opened.replace(tzinfo=timezone.utc).isoformat() if dt_opened and not dt_opened.tzinfo else (dt_opened.isoformat() if dt_opened else None),
            "ai_done": list_ai_done,
            "tiles_ready": bool(dict_doc.get("bool_tiles_ready")),
        })

    return {
        "recent_slides": list_recent_out,
        "total_slides": dict_stats["int_total_slides"],
        "status_counts": dict_stats["dict_status_counts"],
        "ai_counts": dict_stats["dict_ai_counts"],
        "folder_count": dict_stats["int_folder_count"],
        "storage_used_bytes": dict_stats["int_storage_used_bytes"],
        "storage_total_bytes": dict_stats["int_storage_total_bytes"],
    }


def _empty_cell_annotation_summary() -> dict:
    zero = {
        "total": 0,
        "completed": 0,
        "rejected": 0,
        "percent": 0,
        "running": False,
        "state": "before",
    }
    return {
        "annotation": dict(zero),
        "review": dict(zero),
        "termination": dict(zero),
    }


def _cell_summary_from_patches(patches: list[dict]) -> dict:
    total = len(patches)

    def workflow(patch: dict) -> tuple[str, str, str]:
        status = str(patch.get("str_status") or "")
        annotation = str(patch.get("str_annotation_status") or "")
        review = str(patch.get("str_review_status") or "")
        termination = str(patch.get("str_termination_status") or "")
        if not annotation:
            if status == "completed":
                annotation = "completed"
                review = review or "current"
            elif status == "reviewed":
                annotation = "completed"
                review = review or "reviewed"
                termination = termination or "current"
            elif status == "rejected":
                annotation = "completed"
                review = review or "rejected"
                termination = termination or "current"
            elif status == "in_progress":
                annotation = "in_progress"
            elif status == "required":
                annotation = "required"
        return annotation or "required", review or "pending", termination or "pending"

    def percent(count: int) -> int:
        return round((count / total) * 100) if total else 0

    annotation_completed = [p for p in patches if workflow(p)[0] in {"completed", "reviewed", "rejected"}]
    annotation_running = any(workflow(p)[0] == "in_progress" or p.get("str_status") == "in_progress" for p in patches)
    review_completed = [p for p in patches if workflow(p)[1] in {"reviewed", "rejected"}]
    review_rejected = [p for p in patches if workflow(p)[1] == "rejected"]
    review_running = any(workflow(p)[1] == "current" for p in patches)
    termination_completed = [p for p in patches if workflow(p)[2] == "completed"]
    termination_running = any(workflow(p)[2] == "current" for p in patches)

    annotation_state = "before"
    if total and len(annotation_completed) >= total:
        annotation_state = "completed"
    elif total or annotation_running:
        annotation_state = "running"

    review_state = "before"
    if review_rejected:
        review_state = "rejected"
    elif total and len(review_completed) >= total:
        review_state = "completed"
    elif total and len(annotation_completed) >= total and (review_running or review_completed):
        review_state = "running"

    termination_state = "before"
    if total and len(termination_completed) >= total:
        termination_state = "completed"
    elif total and len(review_completed) >= total and (termination_running or termination_completed):
        termination_state = "running"

    return {
        "annotation": {
            "total": total,
            "completed": len(annotation_completed),
            "rejected": 0,
            "percent": percent(len(annotation_completed)),
            "running": annotation_running,
            "state": annotation_state,
        },
        "review": {
            "total": total,
            "completed": len(review_completed),
            "rejected": len(review_rejected),
            "percent": percent(len(review_completed)),
            "running": review_running,
            "state": review_state,
        },
        "termination": {
            "total": total,
            "completed": len(termination_completed),
            "rejected": 0,
            "percent": percent(len(termination_completed)),
            "running": termination_running,
            "state": termination_state,
        },
    }


async def _cell_annotation_summaries_for_slides(db, slide_ids: list[str]) -> dict[str, dict]:
    if not slide_ids:
        return {}
    grouped: dict[str, list[dict]] = {slide_id: [] for slide_id in slide_ids}
    cursor = db.patch_annotation_status.find(
        {
            "str_slide_id": {"$in": slide_ids},
            "str_status": {"$ne": "not_required"},
        },
        {
            "_id": 0,
            "str_slide_id": 1,
            "str_status": 1,
            "str_annotation_status": 1,
            "str_review_status": 1,
            "str_termination_status": 1,
        },
    )
    async for patch in cursor:
        slide_id = patch.get("str_slide_id")
        if slide_id in grouped:
            grouped[slide_id].append(patch)
    return {
        slide_id: _cell_summary_from_patches(patches) if patches else _empty_cell_annotation_summary()
        for slide_id, patches in grouped.items()
    }


@router.get("/browse")
async def browse(path: str = Query("", description="uploads/ ??? ??? ???")):
    """??? ???????? ??? + ?????? ??? ??? (DB ??ai_results ????????)"""
    target = _safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "???????? ????????")

    folders = []
    slides = []
    list_entries = sorted(target.iterdir())
    set_case_names = {
        _case_name_from_filename(f.name)
        for f in list_entries
        if f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS
    }
    dict_case_clinical = {}
    dict_cell_annotation_summaries = {}

    # DB ??? ??? ??? ?????? ??? ????? ???
    dict_db_slides = await slide_store.list_slides_in_folder(path)
    if is_db_connected() and set_case_names:
        db = get_db()
        for dict_doc in await get_clinical_info_store().find_many(sorted(set_case_names)):
            dict_clinical = dict_doc.get("dict_clinical_info") or {}
            if _has_clinical_info(dict_clinical):
                dict_case_clinical[dict_doc.get("str_case_name", "")] = dict_clinical
        async for dict_doc in db.slides.find({
            "str_case_name": {"$in": sorted(set_case_names)},
            "dict_clinical_info": {"$exists": True},
        }):
            str_case = dict_doc.get("str_case_name") or _case_name_from_filename(dict_doc.get("str_filename", ""))
            dict_clinical = dict_doc.get("dict_clinical_info") or {}
            if str_case not in dict_case_clinical and _has_clinical_info(dict_clinical):
                dict_case_clinical[str_case] = dict_clinical
        list_slide_ids = [
            slide_cache_key(str(f))
            for f in list_entries
            if f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS
        ]
        dict_cell_annotation_summaries = await _cell_annotation_summaries_for_slides(db, list_slide_ids)

    for f in list_entries:
        if f.name.startswith("_chunks_") or f.name.startswith("."):
            continue
        if f.is_dir():
            folders.append({"name": f.name, "type": "folder"})
        elif f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
            slide_id = slide_cache_key(str(f))
            dict_item = {
                "filename": f.name,
                "slide_id": slide_id,
                "case_name": _case_name_from_filename(f.name),
                "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                "type": "slide",
                "annotation_summary": _annotation_summary_for_file_path(str(f)),
            }
            # DB ???? ?????ai_results + ???????? ???
            dict_db = dict_db_slides.get(f.name)
            if dict_db:
                dict_ai = dict_db.get("dict_ai_results") or slide_store._empty_ai_results()
                dict_item["ai_results"] = {
                    str_k: {
                        "has_result": bool(v.get("bool_has_result")),
                        "variants": list(v.get("list_variants") or []),
                    }
                    for str_k, v in dict_ai.items()
                }
                dict_item["uploaded_by"] = dict_db.get("str_uploaded_by") or ""
                dt_opened = dict_db.get("dt_last_opened_at")
                dict_item["last_opened_at"] = dt_opened.replace(tzinfo=timezone.utc).isoformat() if dt_opened and not dt_opened.tzinfo else (dt_opened.isoformat() if dt_opened else None)
                dict_item["status"] = dict_db.get("str_status") or ""
                dict_item["ai_status"] = dict_db.get("str_ai_status") or ""
                dict_item["annotation_status"] = dict_db.get("str_annotation_status") or dict_db.get("str_status") or ""
                dict_item["tissue_annotation_status"] = (
                    dict_db.get("str_tissue_annotation_status")
                    or dict_db.get("str_annotation_status")
                    or dict_db.get("str_status")
                    or ""
                )
                dict_item["cell_annotation_status"] = dict_db.get("str_cell_annotation_status") or ""
                dict_item["cell_annotation_summary"] = dict_cell_annotation_summaries.get(slide_id) or _empty_cell_annotation_summary()
                dict_clinical = dict_db.get("dict_clinical_info") or dict_case_clinical.get(dict_item["case_name"], {})
                dict_item["clinical_info"] = dict_clinical
                dict_item["has_clinical_info"] = _has_clinical_info(dict_clinical)
            else:
                dict_item["ai_results"] = None
                dict_item["status"] = ""
                dict_item["ai_status"] = ""
                dict_item["annotation_status"] = ""
                dict_item["tissue_annotation_status"] = ""
                dict_item["cell_annotation_status"] = ""
                dict_item["cell_annotation_summary"] = dict_cell_annotation_summaries.get(slide_id) or _empty_cell_annotation_summary()
                dict_clinical = dict_case_clinical.get(dict_item["case_name"], {})
                dict_item["clinical_info"] = dict_clinical
                dict_item["has_clinical_info"] = _has_clinical_info(dict_clinical)
            slides.append(dict_item)

    return {"path": path, "folders": folders, "slides": slides}


@router.get("/cases")
async def list_cases(
    project: str = Query("", description="Project path under uploads"),
    hospital: str = Query("", description="Project hospital/institution filter"),
    sample_no: str = Query("", description="Case/sample id search"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    sort_by: str = Query("case_name", description="case_name, has_clinical_info, or last_activity"),
    sort_dir: str = Query("asc", description="asc or desc"),
):
    target = _safe_subpath(project) if project else Path(settings.UPLOAD_DIR)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Project path not found")

    dict_project_info = {}
    dict_slide_docs = {}
    dict_case_clinical = {}
    if is_db_connected():
        db = get_db()
        async for dict_doc in db.project_infos.find({}):
            dict_project_info[dict_doc.get("str_project_path", "")] = dict_doc
        for dict_doc in await get_clinical_info_store().list_all():
            str_case = dict_doc.get("str_case_name", "")
            if str_case:
                dict_case_clinical[str_case] = dict_doc
        async for dict_doc in db.slides.find({}):
            str_rel = (dict_doc.get("str_rel_path") or "").replace("\\", "/").strip("/")
            str_filename = dict_doc.get("str_filename") or ""
            if str_filename:
                dict_slide_docs[f"{str_rel}/{str_filename}".strip("/")] = dict_doc

    str_sample_filter = sample_no.strip().lower()
    str_hospital_filter = hospital.strip().lower()
    dict_cases = {}
    upload_root = Path(settings.UPLOAD_DIR)
    for file_path in target.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in settings.SUPPORTED_EXTENSIONS:
            continue
        try:
            rel_parts = file_path.relative_to(upload_root).parts
        except Exception:
            rel_parts = file_path.parts
        if any(part.startswith(".") or part.startswith("_chunks_") for part in rel_parts):
            continue
        str_rel = _rel_path_for(str(file_path))
        str_project = str_rel.split("/", 1)[0] if str_rel else ""
        dict_proj = dict_project_info.get(str_project) or {}
        str_hospital = dict_proj.get("str_institution", "")
        if str_hospital_filter and str_hospital_filter not in str_hospital.lower():
            continue
        str_case_name = _case_name_from_filename(file_path.name)
        if str_sample_filter and str_sample_filter not in str_case_name.lower() and str_sample_filter not in file_path.name.lower():
            continue
        str_key = f"{str_rel}/{file_path.name}".strip("/")
        dict_doc = dict_slide_docs.get(str_key) or {}
        dict_case = dict_cases.setdefault(str_case_name, {
            "case_name": str_case_name,
            "project": str_project,
            "hospital": str_hospital,
            "slides": [],
            "last_activity": None,
            "last_activity_ts": 0,
            "clinical_info": {},
            "has_clinical_info": False,
            "ai_status": "",
            "has_ai_result": False,
        })
        float_mtime = file_path.stat().st_mtime
        if float_mtime > dict_case["last_activity_ts"]:
            dict_case["last_activity_ts"] = float_mtime
            dict_case["last_activity"] = datetime.fromtimestamp(float_mtime, timezone.utc).date().isoformat()
            dict_case["last_activity_detail"] = datetime.fromtimestamp(float_mtime, timezone.utc).isoformat()
        dt_doc = dict_doc.get("dt_updated_at") or dict_doc.get("dt_last_opened_at") or dict_doc.get("dt_uploaded_at")
        if dt_doc and dt_doc.timestamp() > dict_case["last_activity_ts"]:
            dict_case["last_activity_ts"] = dt_doc.timestamp()
            dict_case["last_activity"] = dt_doc.date().isoformat()
            dict_case["last_activity_detail"] = dt_doc.isoformat()
        str_ai_status = dict_doc.get("str_ai_status") or ""
        if str_ai_status == "in_progress":
            dict_case["ai_status"] = "in_progress"
        dict_ai = dict_doc.get("dict_ai_results") or {}
        bool_has_ai = any((v or {}).get("bool_has_result") for v in dict_ai.values())
        if bool_has_ai:
            dict_case["has_ai_result"] = True
            if dict_case["ai_status"] != "in_progress":
                dict_case["ai_status"] = "done"
        dict_case["slides"].append({
            "filename": file_path.name,
            "path": str_rel,
            "slide_id": slide_cache_key(str(file_path)),
            "size_mb": round(file_path.stat().st_size / 1024 / 1024, 1),
            "ai_status": str_ai_status,
            "has_ai_result": bool_has_ai,
        })

    for str_case_name, dict_case in dict_cases.items():
        dict_case_doc = dict_case_clinical.get(str_case_name) or {}
        dict_clinical = dict_case_doc.get("dict_clinical_info") or {}
        if not dict_clinical and dict_case["slides"]:
            first_slide = dict_case["slides"][0]
            dict_slide_doc = dict_slide_docs.get(f"{first_slide.get('path', '')}/{first_slide.get('filename', '')}".strip("/")) or {}
            dict_clinical = dict_slide_doc.get("dict_clinical_info") or {}
        dict_case["clinical_info"] = dict_clinical
        dict_case["has_clinical_info"] = _has_clinical_info(dict_clinical)
        dict_case["year"] = (dict_case["last_activity"] or "")[:4]
        dict_case["slides"].sort(key=lambda d: d.get("filename", "").lower())

    str_sort_by = sort_by if sort_by in {"case_name", "has_clinical_info", "last_activity"} else "case_name"
    bool_reverse = sort_dir.lower() == "desc"
    if str_sort_by == "has_clinical_info":
        def _sort_key(dict_item: dict):
            return (0 if dict_item.get("has_clinical_info") else 1, (dict_item.get("case_name") or "").lower())
    elif str_sort_by == "last_activity":
        def _sort_key(dict_item: dict):
            return (dict_item.get("last_activity_ts") or 0, (dict_item.get("case_name") or "").lower())
    else:
        def _sort_key(dict_item: dict):
            return ((dict_item.get("case_name") or "").lower(),)
    list_cases_out = sorted(dict_cases.values(), key=_sort_key, reverse=bool_reverse)
    int_total = len(list_cases_out)
    int_start = (page - 1) * page_size
    list_page = list_cases_out[int_start:int_start + page_size]
    for idx, dict_case in enumerate(list_page, start=int_start + 1):
        dict_case["no"] = idx

    list_projects = []
    for p in _list_project_dirs():
        dict_info = dict_project_info.get(p.name) or {}
        dict_public_info = _project_public_info(dict_info)
        list_projects.append({
            "name": p.name,
            "path": p.name,
            "display_name": dict_public_info.get("title") or p.name,
            "hospital": dict_info.get("str_institution", ""),
            "info": dict_public_info,
        })
    list_hospitals = sorted({
        (dict_info.get("str_institution") or "").strip()
        for dict_info in dict_project_info.values()
        if (dict_info.get("str_institution") or "").strip()
    })
    return {
        "cases": list_page,
        "projects": list_projects,
        "hospitals": list_hospitals,
        "total": int_total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/cases/{case_name}/clinical-info", dependencies=[Depends(require_not_viewer)])
async def update_case_clinical_info(case_name: str, payload: dict = Body(...)):
    if not is_db_connected():
        raise HTTPException(503, "Database is not connected")
    dict_raw = payload.get("dict_clinical_info", payload)
    dict_clinical_info = _normalize_clinical_info(dict_raw)
    db = get_db()
    await _upsert_case_clinical_info(db, case_name, dict_clinical_info)
    return {
        "case_name": case_name,
        "dict_clinical_info": dict_clinical_info,
        "has_clinical_info": _has_clinical_info(dict_clinical_info),
    }


# ?? ???????? ??? ??? ????? ??? ??

@router.post("/open-by-name")
async def open_slide_by_name(
    filename: str = Form(...),
    path: str = Form(""),
):
    """???????? ???? ????? ??? ????????. ?????? ???/??????/??? ??? ???."""
    filename = _safe_filename(filename)
    final_path = _safe_subpath(path) / filename
    if not final_path.exists() and Path(filename).suffix.lower() in {".jpg", ".jpeg"}:
        path_converted = converted_tiff_path(final_path)
        if path_converted.exists():
            final_path = path_converted
            filename = path_converted.name
    if not final_path.exists():
        return {"exists": False}
    return {
        "exists": True,
        "filename": filename,
        "size_bytes": final_path.stat().st_size,
        "size_mb": round(final_path.stat().st_size / 1024 / 1024, 1),
    }


@router.post("/open")
async def open_slide(
    request: Request,
    filename: str = Form(...),
    path: str = Form(""),
    open_page: str = Form("ai"),
    dict_user: dict = Depends(get_current_user),
):
    """??????????? ?????? ???? ??? ?????????? ???"""
    filename = _safe_filename(filename)
    final_path = _safe_subpath(path) / filename
    if not final_path.exists():
        return {"exists": False}

    slide_id = slide_cache_key(str(final_path))
    resp = await _open_and_generate(slide_id, str(final_path), filename, dict_user, str_last_opened_page=open_page)
    resp["exists"] = True

    # ?????? ??? ??? ??? ????? ?????
    try:
        await log_audit_event(
            str_action="slide.view",
            str_user_id=str(dict_user.get("_id", "")),
            str_user_email=dict_user.get("str_login_id", ""),
            str_resource_type="slide",
            str_resource_id=slide_id,
            str_detail=filename,
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
            dict_extra={"str_rel_path": path or ""},
        )
    except Exception:
        pass
    return resp


# ?? ??? ???????

@router.post("/upload/start", dependencies=[Depends(require_not_viewer)])
@audit_activity("slide.upload_started", resource_type="upload", resource_key="upload_id")
async def upload_start(request: Request, filename: str = Form(...), dict_user: dict = Depends(get_current_user)):
    """???????? ??upload_id ???"""
    filename = _safe_filename(filename)
    ext = Path(filename).suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"????? ??? ??? ???: {ext}")

    upload_id = uuid.uuid4().hex[:12]
    chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    return {
        "upload_id": upload_id,
        "filename": filename,
        "chunk_size": settings.CHUNK_SIZE,
    }


@router.post("/upload/chunk", dependencies=[Depends(require_not_viewer)])
@audit_activity("slide.upload_chunk", resource_type="upload", resource_key="upload_id", success=False)
async def upload_chunk(
    request: Request,
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    dict_user: dict = Depends(get_current_user),
):
    """??? ?????????? ??? ??? ??????????? auto_ai ??????."""
    auto_ai.upload_enter()
    try:
        chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
        if not chunk_dir.exists():
            raise HTTPException(404, "????????????? ????????")

        chunk_path = chunk_dir / f"chunk_{chunk_index:06d}"
        content = await chunk.read()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(upload_executor, chunk_path.write_bytes, content)

        return {"chunk_index": chunk_index, "size": len(content)}
    finally:
        auto_ai.upload_exit()


@router.post("/upload/complete", dependencies=[Depends(require_not_viewer)])
@audit_activity("slide.upload", resource_type="upload", resource_key="upload_id", success=False)
async def upload_complete(
    request: Request,
    upload_id: str = Form(...),
    filename: str = Form(...),
    total_chunks: int = Form(...),
    path: str = Form(""),
    wait_tiles: str = Form("false"),
    dict_user: dict = Depends(get_current_user),
):
    """???????? ????? ??? ???????? ??? + ??????"""
    auto_ai.upload_enter()
    try:
        # ????????? ?????? ????? ??? ???????? join ????? ???
        filename = _safe_filename(filename)

        chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
        if not chunk_dir.exists():
            raise HTTPException(404, "????????????? ????????")

        # ??????????(start ??? ??? ???)
        ext = Path(filename).suffix.lower()
        if ext not in settings.SUPPORTED_EXTENSIONS:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            raise HTTPException(400, f"????? ??? ??? ???: {ext}")

        # ??? ????? ?????????? ??? ????? ??? ???
        int_total_bytes = 0
        for i in range(total_chunks):
            chunk_path = chunk_dir / f"chunk_{i:06d}"
            if not chunk_path.exists():
                shutil.rmtree(chunk_dir, ignore_errors=True)
                raise HTTPException(400, f"??? {i} ???")
            int_total_bytes += chunk_path.stat().st_size
        if int_total_bytes > settings.MAX_UPLOAD_BYTES:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            int_limit_gb = settings.MAX_UPLOAD_BYTES / (1024 ** 3)
            raise HTTPException(
                413,
                f"???????? ??? ???: {int_total_bytes / (1024**3):.2f} GB > {int_limit_gb:.2f} GB",
            )

        str_norm_upload_path = path.replace("\\", "/").strip("/")
        if not str_norm_upload_path:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            raise HTTPException(400, "Project path is required for uploads")
        str_project = str_norm_upload_path.split("/", 1)[0]
        if not (Path(settings.UPLOAD_DIR) / str_project).is_dir():
            shutil.rmtree(chunk_dir, ignore_errors=True)
            raise HTTPException(400, f"Unknown project: {str_project}")

        save_dir = _safe_subpath(path)
        save_dir.mkdir(parents=True, exist_ok=True)
        final_path = save_dir / filename

        bool_newly_written = False
        bool_converted_jpeg = False
        str_source_filename = filename
        str_sha256 = ""
        if final_path.exists():
            shutil.rmtree(chunk_dir, ignore_errors=True)
        else:
            loop = asyncio.get_running_loop()
            str_sha256 = await loop.run_in_executor(
                upload_executor,
                _join_upload_chunks,
                chunk_dir,
                final_path,
                total_chunks,
            )
            shutil.rmtree(chunk_dir, ignore_errors=True)
            bool_newly_written = True

        # Ordinary JPEGs are not random-access WSI files.  Convert them once
        # to a tiled pyramidal BigTIFF so OpenSlide can serve regions without
        # decoding the complete source image for every viewer/AI worker.
        if ext in {".jpg", ".jpeg"}:
            path_converted = converted_tiff_path(final_path)
            bool_created_converted_file = False
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    upload_executor,
                    lambda: convert_jpeg_to_pyramidal_tiff(
                        final_path,
                        path_converted,
                        max_pixels=settings.JPEG_CONVERSION_MAX_PIXELS,
                        jpeg_quality=settings.JPEG_CONVERSION_QUALITY,
                    ),
                )
                bool_created_converted_file = True
                final_path.unlink()
                final_path = path_converted
                filename = path_converted.name
                ext = final_path.suffix.lower()
                bool_converted_jpeg = True
                str_sha256 = ""
            except FileExistsError:
                if bool_newly_written and final_path.exists():
                    final_path.unlink()
                raise HTTPException(
                    409,
                    f"Converted TIFF already exists: {converted_tiff_filename(str_source_filename)}",
                )
            except Exception as exc:
                if bool_created_converted_file and path_converted.exists():
                    try:
                        path_converted.unlink()
                    except OSError:
                        pass
                if bool_newly_written and final_path.exists():
                    final_path.unlink()
                raise HTTPException(400, f"JPG to pyramidal TIFF conversion failed: {exc}")

        # ??? ??????????? ??? (DB???????? ???)
        if not str_sha256 and final_path.exists():
            loop = asyncio.get_running_loop()
            str_sha256 = await loop.run_in_executor(upload_executor, _hash_file, final_path)

        slide_id = slide_cache_key(str(final_path))
        bool_wait = wait_tiles.lower() in ("true", "1", "yes")
        try:
            resp = await _open_and_generate(
                slide_id, str(final_path), filename, dict_user,
                bool_wait_for_tiles=bool_wait,
                str_sha256=str_sha256,
            )
            resp["converted_from_jpeg"] = bool_converted_jpeg
            if bool_converted_jpeg:
                resp["source_filename"] = str_source_filename
            await _log_management_event(
                request,
                dict_user,
                str_action="slide.upload",
                str_resource_type="slide",
                str_resource_id=slide_id,
                str_detail=f"Uploaded slide {filename} to {str_norm_upload_path}",
                dict_extra={
                    "str_upload_id": upload_id,
                    "int_total_chunks": total_chunks,
                    "str_filename": filename,
                    "str_rel_path": str_norm_upload_path,
                    "str_project": str_project,
                    "int_size_bytes": int_total_bytes,
                    "str_sha256": str_sha256,
                    "bool_new_file": bool_newly_written,
                    "bool_converted_from_jpeg": bool_converted_jpeg,
                    "str_source_filename": str_source_filename,
                    "int_stored_size_bytes": final_path.stat().st_size,
                },
                dict_after={
                    "filename": filename,
                    "path": str_norm_upload_path,
                    "sha256": str_sha256,
                    "new_file": bool_newly_written,
                    "converted_from_jpeg": bool_converted_jpeg,
                    "source_filename": str_source_filename,
                },
            )
            return resp
        except HTTPException as exc:
            # OpenSlide/Philips open failures mean the uploaded payload is not usable.
            if final_path.suffix.lower() == ".zip":
                cleanup_dicom_archive_cache(final_path)
            if bool_newly_written and final_path.exists():
                try:
                    final_path.unlink()
                except Exception:
                    pass
            detail = str(exc.detail) if getattr(exc, "detail", None) else "Unsupported slide file"
            raise HTTPException(400, detail)
    finally:
        auto_ai.upload_exit()


# ?? ??? ??? ??? ??? ??

@router.post("/open-local")
async def open_local_file(
    request: Request,
    file_path: str = Form(...),
    dict_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """??? ??? ?????? WSI ??? ???.

    file_path ???????UPLOAD_DIR ?????? ??? ??admin ?????/etc/passwd.svs
    ??? ??? ???????? ?????? ???????????.
    """
    path = Path(file_path).resolve()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    try:
        path.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(400, "uploads/ ??? ??????????? ??????")
    if not path.exists():
        raise HTTPException(404, f"??????????? ??????: {path.name}")

    ext = path.suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"????? ??? ??? ???: {ext}")

    slide_id = slide_cache_key(str(path))
    resp = await _open_and_generate(slide_id, str(path), path.name, dict_user)
    try:
        await log_audit_event(
            str_action="slide.view",
            str_user_id=str(dict_user.get("_id", "")),
            str_user_email=dict_user.get("str_login_id", ""),
            str_resource_type="slide",
            str_resource_id=slide_id,
            str_detail=path.name,
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
            dict_extra={"str_source": "open-local"},
        )
    except Exception:
        pass
    return resp


# ?? ?????? ??? ??? ??

@router.get("/tile-progress/{slide_id}")
async def get_tile_progress(slide_id: str):
    """????????????????? ??? (slide_id??filename ???)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "??????????? ????????")
    filename = Path(info.file_path).name
    progress = tile_generator.get_progress(filename, info.file_path)
    if progress is None:
        raise HTTPException(404, "?????? ???????? ????????")
    return progress


# ?? ?????? ??? ??

@router.get("/{slide_id}/info")
async def get_slide_info(slide_id: str):
    """?????? ???????????"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "??????????? ????????")

    return {
        "slide_id": slide_id,
        "file_path": info.file_path,
        "dimensions": info.dimensions,
        "level_count": info.level_count,
        "level_dimensions": info.level_dimensions,
        "level_downsamples": info.level_downsamples,
        "stage_count": info.stage_count,
        "stage_downsamples": info.stage_downsamples,
        "stage_dimensions": info.stage_dimensions,
        "mpp": info.mpp,
        "mpp_x": info.mpp_x,
        "mpp_y": info.mpp_y,
        "vendor": info.vendor,
        "objective_power": info.objective_power,
        "physical_width_mm": info.physical_width_mm,
        "physical_height_mm": info.physical_height_mm,
        "tiles_ready": tile_generator.tiles_marker_matches_file(Path(info.file_path).name, info.file_path),
    }


@router.get("/{slide_id}/clinical-info")
async def get_slide_clinical_info(slide_id: str):
    """Return per-case clinical score metadata shared by AI and annotation viewers."""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Slide not found")
    if not is_db_connected():
        return {"slide_id": slide_id, "dict_clinical_info": {}}

    db = get_db()
    str_rel_path = _rel_path_for(info.file_path)
    str_filename = Path(info.file_path).name
    str_case_name = _case_name_from_filename(str_filename)
    dict_doc = await db.slides.find_one({"str_slide_id": slide_id})
    if not dict_doc:
        dict_doc = await db.slides.find_one({
            "str_rel_path": str_rel_path,
            "str_filename": str_filename,
        })
    dict_clinical = await _get_case_clinical_info(db, str_case_name)
    return {
        "slide_id": slide_id,
        "case_name": str_case_name,
        "dict_clinical_info": dict_clinical or (dict_doc or {}).get("dict_clinical_info") or {},
    }


@router.patch("/{slide_id}/clinical-info", dependencies=[Depends(require_not_viewer)])
async def update_slide_clinical_info(slide_id: str, payload: dict = Body(...)):
    """Store per-case clinical score metadata shared by AI and annotation viewers."""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Slide not found")
    if not is_db_connected():
        raise HTTPException(503, "Database is not connected")

    dict_raw = payload.get("dict_clinical_info", payload)
    dict_clinical_info = _normalize_clinical_info(dict_raw)

    db = get_db()
    str_rel_path = _rel_path_for(info.file_path)
    str_filename = Path(info.file_path).name
    str_case_name = _case_name_from_filename(str_filename)
    dt_now = datetime.now(timezone.utc)
    await _upsert_case_clinical_info(db, str_case_name, dict_clinical_info)
    result = await db.slides.update_many(
        {"$or": [
            {"str_case_name": str_case_name},
            {"str_filename": {"$regex": _case_filename_regex(str_case_name)}},
        ]},
        {"$set": {
            "str_case_name": str_case_name,
            "dict_clinical_info": dict_clinical_info,
            "dt_updated_at": dt_now,
        }},
    )
    if result.matched_count == 0:
        await db.slides.update_one(
            {"str_rel_path": str_rel_path, "str_filename": str_filename},
            {
                "$set": {
                    "str_slide_id": slide_id,
                    "str_case_name": str_case_name,
                    "str_full_path": info.file_path,
                    "dict_clinical_info": dict_clinical_info,
                    "dt_updated_at": dt_now,
                },
                "$setOnInsert": {
                    "str_rel_path": str_rel_path,
                    "str_filename": str_filename,
                    "dt_created_at": dt_now,
                    "dict_ai_results": slide_store._empty_ai_results(),
                },
            },
            upsert=True,
        )

    return {
        "slide_id": slide_id,
        "case_name": str_case_name,
        "dict_clinical_info": dict_clinical_info,
    }


@router.get("/{slide_id}/verify-integrity")
async def verify_slide_integrity(slide_id: str, dict_user: dict = Depends(get_current_user)):
    """?????? ?????SHA-256 ?????? ????????DB ?????????."""
    from app.database import get_db as _get_db

    db = _get_db()
    dict_doc = await db.slides.find_one({"str_slide_id": slide_id})
    if not dict_doc:
        raise HTTPException(404, "?????? DB ????????")

    str_stored_hash = dict_doc.get("str_sha256", "")
    str_file_path = dict_doc.get("str_full_path", "")
    if not str_file_path or not Path(str_file_path).exists():
        raise HTTPException(404, "?????? ???????? ????????")

    # ?????
    sha256_hash = hashlib.sha256()
    with open(str_file_path, "rb") as f:
        while True:
            bytes_block = f.read(8192)
            if not bytes_block:
                break
            sha256_hash.update(bytes_block)
    str_current_hash = sha256_hash.hexdigest()

    bool_match = str_stored_hash == str_current_hash if str_stored_hash else False

    # ???? ???? ?????????????
    if not str_stored_hash:
        await db.slides.update_one(
            {"str_slide_id": slide_id},
            {"$set": {"str_sha256": str_current_hash}},
        )

    return {
        "slide_id": slide_id,
        "filename": dict_doc.get("str_filename", ""),
        "str_stored_hash": str_stored_hash or "(not set ??saved now)",
        "str_current_hash": str_current_hash,
        "bool_integrity_ok": bool_match if str_stored_hash else True,
    }


# ?? ??? / ??? ??

@router.get("/")
async def list_slides():
    """??? ?????? ???"""
    return slide_manager.list_slides()


# ???????????????????????????????????????????????????????????????????????????????????
# ?????AI ??? ??? ??? ??folder_ai_configs ?????
# ???????????????????????????????????????????????????????????????????????????????????

from datetime import datetime, timezone
from app.database import get_db, is_db_connected


def _norm_folder_path(str_path: str) -> str:
    if not str_path:
        return ""
    return str_path.replace("\\", "/").strip("/")


def _project_path_from_folder(str_norm: str) -> str:
    str_norm = (str_norm or "").replace("\\", "/").strip("/")
    if not str_norm:
        return ""
    return str_norm.split("/", 1)[0]


async def _clone_legacy_folder_config(db, str_norm: str) -> Optional[dict]:
    """Restore a pre-project folder config for a project-prefixed folder path."""
    if not str_norm or "/" not in str_norm:
        return None

    str_legacy = str_norm.split("/", 1)[1]
    if not str_legacy:
        return None

    dict_legacy = await db.folder_ai_configs.find_one({"str_rel_path": str_legacy})
    if not dict_legacy:
        return None

    dt_now = datetime.now(timezone.utc)
    await db.folder_ai_configs.update_one(
        {"str_rel_path": str_norm},
        {
            "$set": {
                "bool_enabled": bool(dict_legacy.get("bool_enabled", False)),
                "list_tasks": dict_legacy.get("list_tasks") or [],
                "dt_updated_at": dt_now,
                "str_restored_from_path": str_legacy,
            },
            "$setOnInsert": {
                "str_rel_path": str_norm,
                "dt_created_at": dt_now,
            },
        },
        upsert=True,
    )
    return await db.folder_ai_configs.find_one({"str_rel_path": str_norm})


@router.get("/folder-config")
async def get_folder_config(path: str = Query("")):
    """?????AI ??? ??? ??? ??? ???????????????."""
    if not is_db_connected():
        return {"path": path, "enabled": False, "tasks": []}
    db = get_db()
    str_norm = _norm_folder_path(path)
    dict_doc = await db.folder_ai_configs.find_one({"str_rel_path": str_norm})
    if not dict_doc:
        dict_doc = await _clone_legacy_folder_config(db, str_norm)
    if not dict_doc:
        str_project = _project_path_from_folder(str_norm)
        if str_project:
            dict_project = await db.project_infos.find_one({"str_project_path": str_project})
            list_project_tasks = _clean_ai_tasks((dict_project or {}).get("list_project_ai_tasks") or [])
            if dict_project and dict_project.get("bool_project_ai_enabled") and list_project_tasks:
                return {
                    "path": str_norm,
                    "enabled": True,
                    "tasks": list_project_tasks,
                    "source": "project",
                    "inherited": True,
                    "project": str_project,
                }
        return {"path": str_norm, "enabled": False, "tasks": [], "source": "none", "inherited": False}
    list_out = []
    for t in (dict_doc.get("list_tasks") or []):
        dict_task = {"model": t.get("model", ""), "variant": t.get("variant", "")}
        if t.get("target_mpp") is not None:
            dict_task["target_mpp"] = float(t.get("target_mpp"))
        list_out.append(dict_task)
    return {
        "path": str_norm,
        "enabled": bool(dict_doc.get("bool_enabled", False)),
        "tasks": list_out,
        "source": "folder",
        "inherited": False,
    }


@router.post("/folder-config", dependencies=[Depends(require_not_viewer)])
async def save_folder_config(
    request: Request,
    path: str = Form(""),
    enabled: bool = Form(True),
    tasks_json: str = Form("[]"),
    dict_user: dict = Depends(get_current_user),
):
    """?????AI ??? ??? ??? ????????

    tasks_json: JSON array ??`[{"model": "Quanti HE", "variant": "Stomach"}, ...]`
      model ? {Quanti HE, Quanti PD-L1, Quanti IHC} ?????, variant ??tissue_type/marker.
    """
    if not is_db_connected():
        raise HTTPException(503, "DB ??? ???")

    try:
        list_raw = json.loads(tasks_json)
        if not isinstance(list_raw, list):
            raise ValueError("tasks_json must be a JSON array")
    except Exception as e:
        raise HTTPException(400, f"?????tasks_json: {e}")

    dict_legacy_models = {
        "HE-Fit": "Quanti HE",
        "PD-Score": "Quanti PD-L1",
        "Precise-IHC": "Quanti IHC",
        "VS-IHC": "VS IHC",
    }
    set_allowed_models = {"Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC"}
    list_clean = []
    for dict_t in list_raw:
        if not isinstance(dict_t, dict):
            continue
        str_model = str(dict_t.get("model", "")).strip()
        str_variant = str(dict_t.get("variant", "")).strip()
        str_model = dict_legacy_models.get(str_model, str_model)
        if str_model not in set_allowed_models or not str_variant:
            continue
        dict_entry = {"model": str_model, "variant": str_variant}
        if str_model == "VS IHC":
            try:
                float_mpp = float(dict_t.get("target_mpp", 2.0))
            except (TypeError, ValueError):
                float_mpp = 2.0
            dict_entry["target_mpp"] = float_mpp
        list_clean.append(dict_entry)

    db = get_db()
    str_norm = _norm_folder_path(path)
    dict_before = await db.folder_ai_configs.find_one({"str_rel_path": str_norm})
    dt_now = datetime.now(timezone.utc)
    await db.folder_ai_configs.update_one(
        {"str_rel_path": str_norm},
        {
            "$set": {
                "bool_enabled": bool(enabled),
                "list_tasks": list_clean,
                "dt_updated_at": dt_now,
            },
            "$setOnInsert": {
                "str_rel_path": str_norm,
                "dt_created_at": dt_now,
            },
        },
        upsert=True,
    )
    await _log_management_event(
        request,
        dict_user,
        str_action="folder.ai_config_update",
        str_resource_type="folder",
        str_resource_id=str_norm,
        str_detail=f"Updated auto AI config for {str_norm or 'root'}",
        dict_extra={"str_rel_path": str_norm, "bool_enabled": bool(enabled), "list_tasks": list_clean},
        dict_before={
            "enabled": bool(dict_before.get("bool_enabled")) if dict_before else None,
            "tasks": dict_before.get("list_tasks") if dict_before else [],
        },
        dict_after={"enabled": bool(enabled), "tasks": list_clean},
    )
    return {"status": "saved", "path": str_norm, "enabled": enabled, "tasks": list_clean}


@router.delete("/folder-config", dependencies=[Depends(require_not_viewer)])
async def delete_folder_config(
    request: Request,
    path: str = Query(""),
    dict_user: dict = Depends(get_current_user),
):
    """?????AI ??? ??? ??? ???."""
    if not is_db_connected():
        raise HTTPException(503, "DB ??? ???")
    db = get_db()
    str_norm = _norm_folder_path(path)
    dict_before = await db.folder_ai_configs.find_one({"str_rel_path": str_norm})
    await db.folder_ai_configs.delete_one({"str_rel_path": str_norm})
    await _log_management_event(
        request,
        dict_user,
        str_action="folder.ai_config_delete",
        str_resource_type="folder",
        str_resource_id=str_norm,
        str_detail=f"Deleted auto AI config for {str_norm or 'root'}",
        dict_extra={"str_rel_path": str_norm},
        dict_before={
            "enabled": bool(dict_before.get("bool_enabled")) if dict_before else None,
            "tasks": dict_before.get("list_tasks") if dict_before else [],
        },
    )
    return {"status": "deleted", "path": str_norm}


@router.delete("/{slide_id}")
async def close_slide(slide_id: str):
    """?????? ???"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "??????????? ????????")

    await asyncio.to_thread(slide_manager.close, slide_id)
    return {"status": "closed", "slide_id": slide_id}


# ?? Annotation ????????? ??

_INT_ANNOTATIONS_MAX_BYTES = 8 * 1024 * 1024  # 8 MB ??annotation ???????? ?????
_INT_ANNOTATION_CLASSES_MAX_BYTES = 256 * 1024
_DEFAULT_ANNOTATION_CLASSES = [
    {"id": "default", "name": "Default", "color": [0, 255, 0]},
]


def _annotation_slide_dirname(filename: str) -> str:
    """?????? ?????? annotations ??? ?????????????? ???"""
    str_name = Path(filename).name.strip()
    if not str_name:
        str_name = "slide"
    for ch in '<>:"/\\|?*':
        str_name = str_name.replace(ch, "_")
    str_name = "".join("_" if ord(ch) < 32 else ch for ch in str_name)
    str_name = str_name.rstrip(" .")
    if str_name in {"", ".", ".."}:
        str_name = hashlib.sha256(filename.encode("utf-8", "ignore")).hexdigest()[:16]
    return str_name


def _annotation_path_for_file_path(file_path: str) -> Path:
    return Path(settings.ANNOTATIONS_DIR) / slide_cache_key(file_path) / "annotations.json"


def _annotation_summary_for_file_path(file_path: str) -> dict:
    ann_path = _annotation_path_for_file_path(file_path)
    if not ann_path.exists():
        return {"has_slide_memo": False, "has_annotation_memo": False, "has_memo": False}
    try:
        with open(ann_path, "r", encoding="utf-8") as f:
            payload = json.loads(f.read())
    except Exception:
        return {"has_slide_memo": False, "has_annotation_memo": False, "has_memo": False}
    if isinstance(payload, dict):
        slide_memo = str(payload.get("slide_memo") or payload.get("memo") or "").strip()
        annotations = payload.get("annotations") if isinstance(payload.get("annotations"), list) else []
    elif isinstance(payload, list):
        meta = next((item for item in payload if isinstance(item, dict) and (item.get("type") == "__meta__" or item.get("kind") == "annotation_meta")), {})
        slide_memo = str(meta.get("slide_memo") or meta.get("memo") or (meta.get("properties") or {}).get("slide_memo") or "").strip()
        annotations = payload
    else:
        slide_memo = ""
        annotations = []
    has_annotation_memo = any(
        isinstance(item, dict)
        and str(item.get("memo") or (item.get("properties") or {}).get("memo") or "").strip()
        for item in annotations
    )
    return {
        "has_slide_memo": bool(slide_memo),
        "has_annotation_memo": bool(has_annotation_memo),
        "has_memo": bool(slide_memo or has_annotation_memo),
    }
