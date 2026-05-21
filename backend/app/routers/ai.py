"""
AI 분석 API — Detection / Quanti PD-L1 / Quanti IHC / Virtual Stain 라우팅 레이어.

워커/모델 로직은 app/ai_pipelines/ 패키지로 분리되어 있고, 사용자 편집본
라우트는 app/routers/ai_user_edits.py 의 서브 라우터에서 처리한다. 이 모듈은
요청을 받아 task_id 를 발급하고 백그라운드 스레드를 띄우는 얇은 라우팅 레이어다.
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

# 기존 AI 코드 경로 추가 — ai_pipelines 의 워커들이 ai/ 모듈을 import 할 수 있게 한다.
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 공유 task 상태 — 라우트가 새 task 등록 / 조회 시 직접 사용한다.
from app.ai_pipelines.task_state import _tasks, _tasks_lock

# 캐시 경로 — VS 결과 PNG/타일 서빙 라우트에서 사용.
from app.ai_pipelines.cache_paths import (
    get_vs_cache_paths as _get_vs_cache_paths,
    get_vs_tile_dir as _get_vs_tile_dir,
)

# 백그라운드 워커 — threading.Thread(target=...) 로 호출.
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


# Viewer 는 AI 기능 전면 차단 — 트리거/조회/결과 저장 모두 거부.
router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_not_viewer)])

# Virtual stain 타일 전용 서브 라우터 — <img src> 용 ?mt= 티켓 허용.
# main.py 에서 같은 prefix("/api/ai") 로 별도 include 된다.
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
    """Quanti PD-L1 추론 시작 (Stomach → CPS, Lung → TPS)"""
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
    """Quanti IHC 추론 시작 (marker: HER2 / ER_PR / KI_67)"""
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
    """AI 작업 상태 조회.

    완료된 작업의 `result` 는 수백 MB dict 가 될 수 있으므로 JSON 직렬화를
    스레드풀로 오프로드한다. 이벤트 루프에서 직렬화하면 같은 시간 동안
    타일 서빙이 밀린다.
    """
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
        response["has_result"] = task.get("result") is not None
    elif task["status"] == "error":
        response["error"] = task["error"]

    loop = asyncio.get_running_loop()
    bytes_body = await loop.run_in_executor(
        None, lambda: json.dumps(response).encode("utf-8")
    )
    return Response(content=bytes_body, media_type="application/json")


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
    """AI 작업 결과 조회. 대용량 result dict 는 스레드풀에서 직렬화."""
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    if task["status"] != "completed":
        raise HTTPException(400, f"작업 미완료 (status: {task['status']})")

    obj_result = task["result"]
    loop = asyncio.get_running_loop()
    bytes_body = await loop.run_in_executor(
        None, lambda: json.dumps(obj_result).encode("utf-8")
    )
    return Response(content=bytes_body, media_type="application/json")


# 사용자 편집본 라우트(/save-result, /user-edits/*) — ai_user_edits 서브 라우터로 분리.
# 부모 router 의 인증 의존성(get_current_user, require_not_viewer) 을 그대로 상속한다.
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
    """Virtual stain (VS IHC) 작업 시작 (비동기)"""
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
    """Virtual stain 캐시 PNG 서빙 (전체 추론 결과, PDF/리포트용)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
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
    Virtual stain 피라미드 타일 서빙.
    디스크에 있으면 정적 서빙, 없으면 404 (빈/흰 타일은 생성 안 함).
    """
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    tile_dir = _get_vs_tile_dir(info.file_path, target_mpp)
    tile_path = tile_dir / str(level) / f"{tx}_{ty}.jpeg"
    if not tile_path.exists():
        raise HTTPException(404, "tile not found")
    return FileResponse(
        str(tile_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )
