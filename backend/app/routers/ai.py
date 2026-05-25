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
from app.config import settings
from app.database import get_db, is_db_connected
from app.slide_manager import slide_manager

# 기존 AI 코드 경로 추가 — ai_pipelines 의 워커들이 ai/ 모듈을 import 할 수 있게 한다.
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 공유 task 상태 — 라우트가 새 task 등록 / 조회 시 직접 사용한다.
from app.ai_pipelines.task_state import (
    _tasks,
    _tasks_lock,
    cleanup_old_tasks,
    release_task_result,
)

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

def _read_vs_tile_size(path_meta: Path) -> int:
    try:
        if path_meta.exists():
            with open(path_meta, "r", encoding="utf-8") as f:
                dict_meta = json.load(f)
            return max(1, int(dict_meta.get("tile_size") or 512))
    except Exception:
        pass
    return 512


def _try_build_vs_parent_tile(path_tile_dir: Path, int_level: int, int_tx: int,
                              int_ty: int, int_tile_size: int) -> Optional[Path]:
    if int_level <= 0:
        return None
    from PIL import Image

    path_dst = path_tile_dir / str(int_level) / f"{int_tx}_{int_ty}.jpeg"
    path_dst.parent.mkdir(parents=True, exist_ok=True)
    path_src_dir = path_tile_dir / str(int_level - 1)
    if not path_src_dir.exists():
        return None

    img_merged = Image.new("RGB", (int_tile_size * 2, int_tile_size * 2), (255, 255, 255))
    bool_any = False
    for dy in range(2):
        for dx in range(2):
            path_src = path_src_dir / f"{int_tx * 2 + dx}_{int_ty * 2 + dy}.jpeg"
            if not path_src.exists():
                continue
            try:
                with Image.open(path_src) as img_src:
                    img_merged.paste(img_src.convert("RGB"), (dx * int_tile_size, dy * int_tile_size))
                bool_any = True
            except Exception:
                continue

    if not bool_any:
        return None

    resample_box = getattr(getattr(Image, "Resampling", Image), "BOX", Image.BOX)
    img_out = img_merged.resize((int_tile_size, int_tile_size), resample_box)
    img_out.save(str(path_dst), "JPEG", quality=88)
    return path_dst


async def _resolve_vs_slide_path(str_slide_id: str) -> str:
    info = slide_manager.get(str_slide_id)
    if info:
        return info.file_path

    if is_db_connected():
        try:
            db = get_db()
            dict_doc = await db.slides.find_one({"str_slide_id": str_slide_id})
            if dict_doc:
                str_full_path = str(dict_doc.get("str_full_path") or "")
                if str_full_path and Path(str_full_path).exists():
                    return str_full_path
                str_filename = str(dict_doc.get("str_filename") or "")
                str_rel_path = str(dict_doc.get("str_rel_path") or "").strip("/\\")
                if str_filename:
                    path_candidate = Path(settings.UPLOAD_DIR) / str_rel_path / str_filename
                    if path_candidate.exists():
                        return str(path_candidate)
        except Exception:
            pass

    return ""


def _build_vs_tile_manifest(path_tile_dir: Path, path_meta: Path) -> dict:
    dict_manifest = {
        "tile_size": _read_vs_tile_size(path_meta),
        "levels": [],
        "tile_keys": {},
    }
    try:
        if path_meta.exists():
            with open(path_meta, "r", encoding="utf-8") as f:
                dict_meta = json.load(f)
            dict_manifest["tile_size"] = max(1, int(dict_meta.get("tile_size") or dict_manifest["tile_size"]))
            dict_manifest["levels"] = dict_meta.get("levels") or []
    except Exception:
        pass

    dict_level_sets = {}
    list_levels = []
    for dict_level in dict_manifest["levels"]:
        try:
            list_levels.append((int(dict_level.get("level")), dict_level))
        except Exception:
            continue

    for int_level, _dict_level in sorted(list_levels, key=lambda item: item[0]):
        set_keys = set()
        path_level = path_tile_dir / str(int_level)
        if path_level.exists():
            set_keys.update(path_tile.stem for path_tile in path_level.glob("*.jpeg"))
        if int_level > 0 and (int_level - 1) in dict_level_sets:
            for str_key in dict_level_sets[int_level - 1]:
                try:
                    str_tx, str_ty = str_key.split("_", 1)
                    set_keys.add(f"{int(str_tx) // 2}_{int(str_ty) // 2}")
                except Exception:
                    continue
        dict_level_sets[int_level] = set_keys
        dict_manifest["tile_keys"][str(int_level)] = sorted(set_keys)

    for dict_level in dict_manifest["levels"]:
        try:
            int_level = int(dict_level.get("level"))
        except Exception:
            continue
        if str(int_level) not in dict_manifest["tile_keys"]:
            dict_manifest["tile_keys"][str(int_level)] = []
    return dict_manifest


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
    """AI 작업 상태 조회.

    완료된 작업의 `result` 는 수백 MB dict 가 될 수 있으므로 JSON 직렬화를
    스레드풀로 오프로드한다. 이벤트 루프에서 직렬화하면 같은 시간 동안
    타일 서빙이 밀린다.
    """
    cleanup_old_tasks()
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
    """AI 작업 결과 조회. 대용량 result dict 는 스레드풀에서 직렬화."""
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    if task["status"] != "completed":
        raise HTTPException(400, f"작업 미완료 (status: {task['status']})")

    obj_result = task.get("result")
    if obj_result is None:
        raise HTTPException(410, "AI task result has already been released from memory. Run the analysis again or load the cached result.")
    loop = asyncio.get_running_loop()
    bytes_body = await loop.run_in_executor(
        None, lambda: json.dumps(obj_result, separators=(',', ':')).encode("utf-8")
    )
    release_task_result(task_id)
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


@router.get("/virtual-stain/{slide_id}/{stain_type}/tile-manifest")
async def get_virtual_stain_tile_manifest(
    slide_id: str,
    stain_type: str,
    target_mpp: float = Query(2.0),
):
    str_slide_path = await _resolve_vs_slide_path(slide_id)
    if not str_slide_path:
        return {"tile_size": 512, "levels": [], "tile_keys": {}}
    _, meta_path = _get_vs_cache_paths(str_slide_path, target_mpp)
    tile_dir = _get_vs_tile_dir(str_slide_path, target_mpp)
    return _build_vs_tile_manifest(tile_dir, meta_path)


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
    str_slide_path = await _resolve_vs_slide_path(slide_id)
    if not str_slide_path:
        raise HTTPException(404, "slide path not found")
    _, meta_path = _get_vs_cache_paths(str_slide_path, target_mpp)
    tile_dir = _get_vs_tile_dir(str_slide_path, target_mpp)
    int_tile_size = _read_vs_tile_size(meta_path)
    tile_path = tile_dir / str(level) / f"{tx}_{ty}.jpeg"
    if not tile_path.exists():
        tile_path = _try_build_vs_parent_tile(tile_dir, level, tx, ty, int_tile_size)
    if not tile_path or not tile_path.exists():
        raise HTTPException(404, "tile not found")
    return FileResponse(
        str(tile_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )
