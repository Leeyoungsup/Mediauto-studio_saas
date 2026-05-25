"""
AI text API — Detection / Quanti PD-L1 / Quanti IHC / Virtual Stain text text.

text/text text app/ai_pipelines/ text text text, text text
text app/routers/ai_user_edits.py text text text text. text text
text text task_id text text text text text text text text.
"""
import asyncio
import json
import sys
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from app.audit import get_client_ip, log_audit_event
from app.auth import get_current_user, get_media_user, require_not_viewer
from app.slide_manager import slide_manager

# text AI text text text — ai_pipelines text text ai/ text import text text text text.
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# text task text — text text task text / text text text text.
from app.ai_pipelines.task_state import (
    _tasks,
    _tasks_lock,
    cleanup_old_tasks,
    release_task_result,
)

# text text — VS text PNG/text text text text.
from app.ai_pipelines.cache_paths import (
    get_vs_cache_paths as _get_vs_cache_paths,
    get_vs_tile_dir as _get_vs_tile_dir,
)

# text text — threading.Thread(target=...) text text.
from app.ai_pipelines.detection import run_detection as _run_detection
from app.ai_pipelines.marker_pipeline import (
    run_pd_score as _run_pd_score,
    run_precise_ihc as _run_precise_ihc,
)
from app.ai_pipelines.virtual_stain import (
    VS_MODEL_FILES,
    run_virtual_stain as _run_virtual_stain,
)
from ai.quanti_ihc import PRECISE_IHC_CONFIG
from ai.quanti_pd_l1 import PD_SCORE_CONFIG


# Viewer text AI text text text — text/text/text text text text.
router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_not_viewer)])

# Virtual stain text text text text — <img src> text ?mt= text text.
# main.py text text prefix("/api/ai") text text include text.
media_router = APIRouter(dependencies=[Depends(get_media_user)])


async def _log_ai_analyze(
    request: Request,
    dict_user: dict,
    str_model: str,
    str_variant: str,
    str_slide_id: str,
    str_filename: str,
    str_task_id: str,
) -> None:
    """AI text text text text — text text text."""
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


# ═══ API text ═══

@router.post("/detect")
async def start_detection(
    request: Request,
    slide_id: str = Form(...),
    roi_polygons: Optional[str] = Form(None),
    tissue_type: str = Form("Stomach"),
    dict_user: dict = Depends(get_current_user),
):
    """text text text (text)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")

    task_id = uuid.uuid4().hex[:12]
    polygons = json.loads(roi_polygons) if roi_polygons else None
    str_filename = Path(info.file_path).name

    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued", "progress": 0,
            "result": None, "error": None, "status_msg": "",
            "slide_filename": str_filename,
            "model": "Quanti HE", "variant": tissue_type,
        }

    t = threading.Thread(
        target=_run_detection,
        args=(task_id, slide_id, polygons, tissue_type),
        daemon=True,
    )
    t.start()

    await _log_ai_analyze(request, dict_user, "Quanti HE", tissue_type, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.post("/pd-score")
async def start_pd_score(
    request: Request,
    slide_id: str = Form(...),
    roi_polygons: Optional[str] = Form(None),
    tissue_type: str = Form("Stomach"),
    dict_user: dict = Depends(get_current_user),
):
    """Quanti PD-L1 text text (Stomach → CPS, Lung → TPS)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")
    if tissue_type not in PD_SCORE_CONFIG:
        raise HTTPException(400, f"text text text text: {tissue_type}")

    task_id = uuid.uuid4().hex[:12]
    polygons = json.loads(roi_polygons) if roi_polygons else None
    str_filename = Path(info.file_path).name

    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued", "progress": 0,
            "result": None, "error": None, "status_msg": "",
            "slide_filename": str_filename,
            "model": "Quanti PD-L1", "variant": tissue_type,
        }

    t = threading.Thread(
        target=_run_pd_score,
        args=(task_id, slide_id, polygons, tissue_type),
        daemon=True,
    )
    t.start()

    await _log_ai_analyze(request, dict_user, "Quanti PD-L1", tissue_type, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.post("/precise-ihc")
async def start_precise_ihc(
    request: Request,
    slide_id: str = Form(...),
    roi_polygons: Optional[str] = Form(None),
    marker: str = Form("HER2"),
    dict_user: dict = Depends(get_current_user),
):
    """Quanti IHC text text (marker: HER2 / ER_PR / KI_67)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")
    if marker not in PRECISE_IHC_CONFIG:
        raise HTTPException(400, f"text text marker: {marker}")

    task_id = uuid.uuid4().hex[:12]
    polygons = json.loads(roi_polygons) if roi_polygons else None
    str_filename = Path(info.file_path).name

    with _tasks_lock:
        _tasks[task_id] = {
            "status": "queued", "progress": 0,
            "result": None, "error": None, "status_msg": "",
            "slide_filename": str_filename,
            "model": "Quanti IHC", "variant": marker,
        }

    t = threading.Thread(
        target=_run_precise_ihc,
        args=(task_id, slide_id, polygons, marker),
        daemon=True,
    )
    t.start()

    await _log_ai_analyze(request, dict_user, "Quanti IHC", marker, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.get("/active-tasks")
async def get_active_tasks():
    """text queued/running text AI text text text text text text.

    text text:
        {"active": {filename: [{"model": ..., "variant": ..., "status": ...}, ...], ...}}
    """
    dict_active: dict[str, list] = {}
    cleanup_old_tasks()
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
    """AI text text text.

    text text `result` text text MB dict text text text text JSON text
    text text. text text text text text text
    text text text.
    """
    cleanup_old_tasks()
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "text text text text")

    response = {
        "task_id": task_id,
        "status": task["status"],
        "progress": task["progress"],
        "status_msg": task.get("status_msg", ""),
    }
    if task["status"] == "completed":
        response["has_result"] = task.get("result") is not None
    elif task["status"] == "error":
        response["error"] = task["error"]

    return response


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    """text text AI text text text.

    - queued/running text cancel_requested text text → text text text text
    - text text text text(JSON/PNG/text text)text text text text text text text
    """
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(404, "text text text text")
        str_status = task.get("status")
        if str_status in ("completed", "error", "cancelled"):
            return {"task_id": task_id, "status": str_status, "msg": "already finished"}
        task["cancel_requested"] = True
        task["status_msg"] = "Cancelling..."
    print(f"[cancel] requested for task {task_id}")
    return {"task_id": task_id, "status": "cancelling"}


@router.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    """AI text text text. text result dict text text text."""
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "text text text text")
    if task["status"] != "completed":
        raise HTTPException(400, f"text text (status: {task['status']})")

    obj_result = task.get("result")
    if obj_result is None:
        raise HTTPException(410, "AI task result has already been released from memory. Run the analysis again or load the cached result.")
    loop = asyncio.get_running_loop()
    bytes_body = await loop.run_in_executor(
        None, lambda: json.dumps(obj_result, separators=(',', ':')).encode("utf-8")
    )
    release_task_result(task_id)
    return Response(content=bytes_body, media_type="application/json")


# text text text(/save-result, /user-edits/*) — ai_user_edits text text text.
# text router text text text(get_current_user, require_not_viewer) text text text.
from app.routers.ai_user_edits import router as _user_edits_router
router.include_router(_user_edits_router)


@router.post("/virtual-stain")
async def start_virtual_stain(
    request: Request,
    slide_id: str = Form(...),
    stain_type: str = Form("ihc_membrane"),
    target_mpp: float = Form(2.0),
    roi_polygons: Optional[str] = Form(None),
    dict_user: dict = Depends(get_current_user),
):
    """Virtual stain (VS IHC) text text (text)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")
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
            "model": "VS IHC", "variant": stain_type,
        }

    t = threading.Thread(
        target=_run_virtual_stain,
        args=(task_id, slide_id, polygons, stain_type, target_mpp),
        daemon=True,
    )
    t.start()
    await _log_ai_analyze(request, dict_user, "VS IHC", stain_type, slide_id, str_filename, task_id)
    return {"task_id": task_id, "status": "queued"}


@router.get("/virtual-stain/{slide_id}/{stain_type}.png")
async def get_virtual_stain_image(slide_id: str, stain_type: str,
                                  target_mpp: float = Query(2.0)):
    """Virtual stain text PNG text (text text text, PDF/text)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")
    png_path, _ = _get_vs_cache_paths(info.file_path, target_mpp)
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
    Virtual stain text text text.
    text text text text, text 404 (text/text text text text text).
    """
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")
    tile_dir = _get_vs_tile_dir(info.file_path, target_mpp)
    tile_path = tile_dir / str(level) / f"{tx}_{ty}.jpeg"
    if not tile_path.exists():
        raise HTTPException(404, "tile not found")
    return FileResponse(
        str(tile_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )
