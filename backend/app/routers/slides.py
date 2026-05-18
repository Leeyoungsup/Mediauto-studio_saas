"""
슬라이드 관리 API — 업로드 (청크), 서버 파일 열기, 목록, 정보, 삭제
타일 프리제네레이션 트리거 + 진행 상태 조회
"""

import os
import json
import uuid
import asyncio
import hashlib
import shutil
from datetime import timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.audit import get_client_ip, log_audit_event
from app.auth import get_current_user, get_media_user, require_not_viewer, require_role
from app.config import settings
from app.models import UserRole
from app.slide_manager import slide_manager
from app import tile_generator
from app import slide_store
from app import auto_ai
from app.cpu_layout import bg_executor

router = APIRouter(dependencies=[Depends(get_current_user)])

# 미디어(썸네일/프리뷰) 전용 서브 라우터 — Bearer JWT 또는 ?mt= 티켓 허용.
# 부모 router 와 같은 prefix("/api/slides") 로 main.py 에서 별도 include 된다.
media_router = APIRouter(dependencies=[Depends(get_media_user)])


def _rel_path_for(file_path: str) -> str:
    """uploads/ 기준 상대 폴더 경로 ('' = 루트). 파일명 제외."""
    try:
        upload_dir = Path(settings.UPLOAD_DIR).resolve()
        p = Path(file_path).resolve()
        rel = p.parent.relative_to(upload_dir)
        s = str(rel).replace("\\", "/")
        return "" if s in (".", "") else s
    except Exception:
        return ""


def _slide_response(slide_id: str, info, filename: str):
    """슬라이드 정보 응답 공통 포맷"""
    return {
        "slide_id": slide_id,
        "filename": filename,
        "dimensions": info.dimensions,
        "level_count": info.level_count,
        "level_dimensions": info.level_dimensions,
        "level_downsamples": info.level_downsamples,
        # 3단계 stage 피라미드 (타일 생성/서빙 기준)
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
        "tiles_ready": tile_generator.tiles_ready(filename),
    }


async def _open_and_generate(
    slide_id: str,
    file_path: str,
    filename: str,
    dict_user: Optional[dict] = None,
    bool_wait_for_tiles: bool = False,
    str_sha256: str = "",
):
    """슬라이드 열기 + 타일 생성 → DB 업서트 후 응답 반환.

    `bool_wait_for_tiles=True` 면 업로드 경로에서 호출된 것으로, 타일 프리젠이
    끝날 때까지 기다린 뒤 응답을 돌려준다. 터널/원격 환경에서 on-demand 타일
    생성이 느려 사용자 경험이 나빠지는 것을 방지.
    """
    # 이미 열려있으면 그대로
    existing = slide_manager.get(slide_id)
    if existing:
        await _run_tile_gen(filename, file_path, bool_wait_for_tiles)
        resp = _slide_response(slide_id, existing, filename)
        await _upsert_and_attach(resp, slide_id, file_path, filename, existing, dict_user, str_sha256)
        return resp

    try:
        info = slide_manager.open(slide_id, file_path)
    except Exception as e:
        raise HTTPException(400, f"슬라이드 열기 실패: {e}")

    await _run_tile_gen(filename, file_path, bool_wait_for_tiles)
    resp = _slide_response(slide_id, info, filename)
    await _upsert_and_attach(resp, slide_id, file_path, filename, info, dict_user, str_sha256)
    return resp


async def _run_tile_gen(filename: str, file_path: str, bool_wait: bool) -> None:
    """타일 생성 실행. wait 모드에서는 동기 실행 (bg_executor), 아니면 백그라운드 스레드."""
    if tile_generator.tiles_ready(filename):
        return
    if not bool_wait:
        tile_generator.start_generation(filename, file_path)
        return
    # 동기 실행 — bg_executor 에 올려 이벤트 루프는 안 막는다
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        bg_executor, tile_generator._generate_tiles, filename, file_path
    )
    # mark_tiles_ready 는 _generate_tiles 가 threadsafe 로 예약하지만,
    # 업로드 응답 전에 DB 가 확실히 최신이 되도록 한 번 더 동기 마킹.
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
):
    """slides 컬렉션에 upsert + 응답에 ai_results 플래그 부착 (DB 없으면 no-op)."""
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
    )
    if dict_doc:
        resp["ai_results"] = slide_store.serialize_slide_doc(dict_doc).get("dict_ai_results")
        dt_up = dict_doc.get("dt_uploaded_at")
        resp["uploaded_at"] = dt_up.replace(tzinfo=timezone.utc).isoformat() if dt_up and not dt_up.tzinfo else (dt_up.isoformat() if dt_up else None)
        # SHA-256 체크섬 저장
        if str_sha256 and not dict_doc.get("str_sha256"):
            from app.database import get_db as _get_db
            db = _get_db()
            await db.slides.update_one(
                {"str_slide_id": slide_id, "str_filename": filename},
                {"$set": {"str_sha256": str_sha256}},
            )
        resp["sha256"] = str_sha256 or dict_doc.get("str_sha256", "")


# ── 저장된 슬라이드/폴더 목록 ──

def _safe_subpath(subpath: str) -> Path:
    """uploads/ 하위 경로만 허용 (디렉토리 탈출 방지).

    `startswith` 만으론 unicode normalization / case 차이 / 부모 prefix 충돌
    (예: `/uploads-evil/` 가 `/uploads/` startswith 통과) 이슈가 있을 수 있어
    `Path.is_relative_to` 로 정확히 검사. Python 3.9+ 표준.
    """
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    target = (upload_dir / subpath).resolve()
    try:
        target.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(400, "잘못된 경로")
    return target


def _safe_filename(filename: str) -> str:
    """업로드/이동/삭제 등에 쓰이는 파일명 검증.

    `_safe_subpath(path) / filename` 패턴은 `path` 만 검사하고 `filename` 은
    그대로 join 해 왔다. filename 에 `../`, `/`, `\\`, `\\0`, 빈 문자열 등이
    오면 디렉토리 탈출이 가능하므로 여기서 일괄 거부.
    """
    if not filename:
        raise HTTPException(400, "파일명이 비어 있습니다")
    if "/" in filename or "\\" in filename:
        raise HTTPException(400, "파일명에 경로 구분자를 사용할 수 없습니다")
    if filename in (".", ".."):
        raise HTTPException(400, "잘못된 파일명")
    if "\x00" in filename:
        raise HTTPException(400, "파일명에 NUL 문자가 포함되었습니다")
    if filename.startswith(".") and filename != ".":
        # 숨김파일/특수 dotfile 차단 (".env", ".secrets.json" 등 노출 방지)
        raise HTTPException(400, "숨김 파일명은 허용되지 않습니다")
    return filename


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
    """대시보드 홈: 최근 슬라이드 + AI/상태 통계."""
    list_recent = await slide_store.get_recent_slides(12)
    dict_stats = await slide_store.get_dashboard_stats(bool_include_disk=include_storage)

    list_recent_out = []
    for dict_doc in list_recent:
        dt_opened = dict_doc.get("dt_last_opened_at")
        dict_ai = dict_doc.get("dict_ai_results") or slide_store._empty_ai_results()
        # AI 결과 모델 이름만 추출
        list_ai_done = [
            str_k for str_k, v in dict_ai.items()
            if v.get("bool_has_result")
        ]
        list_recent_out.append({
            "slide_id": dict_doc.get("str_slide_id", ""),
            "filename": dict_doc.get("str_filename", ""),
            "rel_path": dict_doc.get("str_rel_path", ""),
            "size_bytes": dict_doc.get("int_size_bytes", 0),
            "mpp": dict_doc.get("float_mpp"),
            "status": dict_doc.get("str_status", ""),
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


@router.get("/browse")
async def browse(path: str = Query("", description="uploads/ 기준 상대 경로")):
    """현재 폴더의 하위 폴더 + 슬라이드 파일 목록 (DB 의 ai_results 플래그 포함)"""
    target = _safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "폴더를 찾을 수 없습니다")

    folders = []
    slides = []

    # DB 에서 현재 폴더 슬라이드 문서 한 번에 조회
    dict_db_slides = await slide_store.list_slides_in_folder(path)

    for f in sorted(target.iterdir()):
        if f.name.startswith("_chunks_") or f.name.startswith("."):
            continue
        if f.is_dir():
            folders.append({"name": f.name, "type": "folder"})
        elif f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
            slide_id = hashlib.md5(f.name.encode()).hexdigest()[:12]
            dict_item = {
                "filename": f.name,
                "slide_id": slide_id,
                "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                "type": "slide",
            }
            # DB 문서가 있으면 ai_results + 업로드 메타 부착
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
            else:
                dict_item["ai_results"] = None
                dict_item["status"] = ""
                dict_item["ai_status"] = ""
                dict_item["annotation_status"] = ""
            slides.append(dict_item)

    return {"path": path, "folders": folders, "slides": slides}


@router.get("/folder-tree")
async def folder_tree():
    """uploads/ 하위 전체 폴더 트리를 flat list 로 반환 (업로드 폴더 선택용)."""
    upload_root = Path(settings.UPLOAD_DIR)
    list_folders: list[str] = []
    for dirpath, dirnames, _ in os.walk(upload_root):
        # 숨김/임시 폴더 제외
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not d.startswith("_chunks_")]
        for d in sorted(dirnames):
            rel = os.path.relpath(os.path.join(dirpath, d), upload_root)
            list_folders.append(rel.replace("\\", "/"))
    return {"folders": sorted(list_folders)}


def _list_project_dirs() -> list[Path]:
    upload_root = Path(settings.UPLOAD_DIR)
    if not upload_root.exists():
        return []
    return sorted([
        p for p in upload_root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_chunks_")
    ], key=lambda p: p.name.lower())


def _project_public_info(dict_doc: Optional[dict]) -> dict:
    dict_doc = dict_doc or {}
    return {
        "title": dict_doc.get("str_title", ""),
        "institution": dict_doc.get("str_institution", ""),
        "department": dict_doc.get("str_department", ""),
        "owner": dict_doc.get("str_owner", ""),
        "status": dict_doc.get("str_status", "active"),
        "due_date": dict_doc.get("str_due_date", ""),
        "description": dict_doc.get("str_description", ""),
    }


async def _upsert_project_info(
    *,
    str_project_path: str,
    str_title: str = "",
    str_institution: str = "",
    str_department: str = "",
    str_owner: str = "",
    str_status: str = "active",
    str_due_date: str = "",
    str_description: str = "",
) -> None:
    if not is_db_connected():
        return
    db = get_db()
    dt_now = datetime.now(timezone.utc)
    await db.project_infos.update_one(
        {"str_project_path": str_project_path},
        {
            "$set": {
                "str_project_path": str_project_path,
                "str_title": str_title.strip(),
                "str_institution": str_institution.strip(),
                "str_department": str_department.strip(),
                "str_owner": str_owner.strip(),
                "str_status": (str_status or "active").strip(),
                "str_due_date": str_due_date.strip(),
                "str_description": str_description.strip(),
                "dt_updated_at": dt_now,
            },
            "$setOnInsert": {"dt_created_at": dt_now},
        },
        upsert=True,
    )


@router.get("/projects")
async def list_projects():
    """uploads/ 바로 아래 1차 폴더를 프로젝트 목록으로 반환."""
    dict_infos = {}
    dict_metrics = {}
    if is_db_connected():
        db = get_db()
        async for dict_doc in db.project_infos.find({}):
            dict_infos[dict_doc.get("str_project_path", "")] = dict_doc
        async for dict_doc in db.slides.find(
            {},
            {"str_rel_path": 1, "str_status": 1, "str_annotation_status": 1, "dict_ai_results": 1},
        ):
            str_rel = (dict_doc.get("str_rel_path") or "").replace("\\", "/").strip("/")
            str_project = str_rel.split("/", 1)[0] if str_rel else ""
            if not str_project:
                continue
            dict_project = dict_metrics.setdefault(
                str_project,
                {
                    "annotation_count": 0,
                    "review_count": 0,
                    "termination_count": 0,
                    "reviewed_count": 0,
                    "in_progress_count": 0,
                    "ai_analyzed_count": 0,
                },
            )
            str_status = dict_doc.get("str_status") or ""
            str_annotation_status = dict_doc.get("str_annotation_status") or str_status
            if str_annotation_status in {"review", "done", "termination_in_progress", "termination", "flagged"}:
                dict_project["annotation_count"] += 1
            if str_annotation_status in {"termination_in_progress", "termination", "flagged"}:
                dict_project["review_count"] += 1
            if str_annotation_status == "termination":
                dict_project["termination_count"] += 1
            if str_status == "done":
                dict_project["reviewed_count"] += 1
            if str_status in {"pending", "in_progress"}:
                dict_project["in_progress_count"] += 1
            dict_ai = dict_doc.get("dict_ai_results") or {}
            bool_has_ai = False
            for str_model in slide_store.LIST_AI_MODEL_KEYS:
                dict_cur = dict_ai.get(str_model) or {}
                dict_legacy = dict_ai.get(slide_store._legacy_ai_model_key(str_model)) or {}
                if dict_cur.get("bool_has_result") or dict_legacy.get("bool_has_result"):
                    bool_has_ai = True
                    break
            if bool_has_ai:
                dict_project["ai_analyzed_count"] += 1

    list_projects_out = []
    for p in _list_project_dirs():
        int_slide_count = 0
        int_folder_count = 0
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("_chunks_")]
            int_folder_count += len(dirs)
            int_slide_count += sum(
                1 for f in files
                if Path(f).suffix.lower() in settings.SUPPORTED_EXTENSIONS
            )
        list_projects_out.append({
            "name": p.name,
            "path": p.name,
            "slide_count": int_slide_count,
            "folder_count": int_folder_count,
            "annotation_count": dict_metrics.get(p.name, {}).get("annotation_count", 0),
            "review_count": dict_metrics.get(p.name, {}).get("review_count", 0),
            "termination_count": dict_metrics.get(p.name, {}).get("termination_count", 0),
            "reviewed_count": dict_metrics.get(p.name, {}).get("reviewed_count", 0),
            "in_progress_count": dict_metrics.get(p.name, {}).get("in_progress_count", 0),
            "ai_analyzed_count": dict_metrics.get(p.name, {}).get("ai_analyzed_count", 0),
            "info": _project_public_info(dict_infos.get(p.name)),
        })
    return {"projects": list_projects_out}


@router.post("/project/create", dependencies=[Depends(require_not_viewer)])
async def create_project(
    request: Request,
    name: str = Form(...),
    title: str = Form(""),
    institution: str = Form(""),
    department: str = Form(""),
    owner: str = Form(""),
    status: str = Form("active"),
    due_date: str = Form(""),
    description: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    """프로젝트 생성. 프로젝트는 uploads/ 아래 최상위 폴더로 관리한다."""
    name = _safe_filename(name)
    target = _safe_subpath("") / name
    if target.exists():
        raise HTTPException(400, "이미 존재하는 프로젝트입니다")
    target.mkdir(parents=True, exist_ok=True)
    await _upsert_project_info(
        str_project_path=name,
        str_title=title or name,
        str_institution=institution,
        str_department=department,
        str_owner=owner,
        str_status=status,
        str_due_date=due_date,
        str_description=description,
    )
    await _log_management_event(
        request,
        dict_user,
        str_action="project.create",
        str_resource_type="project",
        str_resource_id=name,
        str_detail=f"Created project {name}",
        dict_after={
            "title": title or name,
            "institution": institution,
            "department": department,
            "owner": owner,
            "status": status,
            "due_date": due_date,
            "description": description,
        },
    )
    return {"status": "created", "name": name, "path": name}


@router.post("/project/update", dependencies=[Depends(require_not_viewer)])
async def update_project(
    request: Request,
    name: str = Form(...),
    title: str = Form(""),
    institution: str = Form(""),
    department: str = Form(""),
    owner: str = Form(""),
    status: str = Form("active"),
    due_date: str = Form(""),
    description: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    name = _safe_filename(name)
    target = _safe_subpath(name)
    dict_before = None
    if is_db_connected():
        db = get_db()
        dict_before = _project_public_info(await db.project_infos.find_one({"str_project_path": name}))
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "?꾨줈?앺듃瑜?李얠쓣 ???놁뒿?덈떎")
    await _upsert_project_info(
        str_project_path=name,
        str_title=title or name,
        str_institution=institution,
        str_department=department,
        str_owner=owner,
        str_status=status,
        str_due_date=due_date,
        str_description=description,
    )
    await _log_management_event(
        request,
        dict_user,
        str_action="project.update",
        str_resource_type="project",
        str_resource_id=name,
        str_detail=f"Updated project {name}",
        dict_before=dict_before,
        dict_after={
            "title": title or name,
            "institution": institution,
            "department": department,
            "owner": owner,
            "status": status,
            "due_date": due_date,
            "description": description,
        },
    )
    return {"status": "saved", "name": name, "path": name}


@router.post("/project/rename", dependencies=[Depends(require_not_viewer)])
async def rename_project(
    request: Request,
    name: str = Form(...),
    new_name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    """프로젝트 이름 변경과 DB rel_path 동기화."""
    name = _safe_filename(name)
    new_name = _safe_filename(new_name)
    target = _safe_subpath(name)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    new_target = _safe_subpath("") / new_name
    if new_target.exists():
        raise HTTPException(400, "이미 존재하는 프로젝트 이름입니다")
    target.rename(new_target)
    await slide_store.rename_folder_in_db(name, new_name)
    old_class_dir = Path(settings.ANNOTATIONS_DIR) / "_projects" / _annotation_slide_dirname(name)
    new_class_dir = Path(settings.ANNOTATIONS_DIR) / "_projects" / _annotation_slide_dirname(new_name)
    if old_class_dir.exists() and not new_class_dir.exists():
        new_class_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_class_dir), str(new_class_dir))
    if is_db_connected():
        db = get_db()
        await db.project_infos.update_one(
            {"str_project_path": name},
            {"$set": {
                "str_project_path": new_name,
                "dt_updated_at": datetime.now(timezone.utc),
            }},
        )
    await _log_management_event(
        request,
        dict_user,
        str_action="project.rename",
        str_resource_type="project",
        str_resource_id=new_name,
        str_detail=f"Renamed project {name} to {new_name}",
        dict_extra={"str_old_path": name, "str_new_path": new_name},
        dict_before={"path": name},
        dict_after={"path": new_name},
    )
    return {"status": "renamed", "name": new_name, "path": new_name}


@router.post("/project/move-folder", dependencies=[Depends(require_not_viewer)])
async def move_folder_to_project(
    request: Request,
    src_path: str = Form(...),
    dst_project: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    src_path = src_path.replace("\\", "/").strip("/")
    dst_project = _safe_filename(dst_project)
    if not src_path or "/" not in src_path:
        raise HTTPException(400, "프로젝트 안의 폴더만 이동할 수 있습니다")
    target = _safe_subpath(src_path)
    dst_project_dir = _safe_subpath(dst_project)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "이동할 폴더를 찾을 수 없습니다")
    if not dst_project_dir.exists() or not dst_project_dir.is_dir():
        raise HTTPException(404, "대상 프로젝트를 찾을 수 없습니다")
    dst_path = dst_project_dir / target.name
    if dst_path.exists():
        raise HTTPException(400, "대상 프로젝트에 같은 이름의 폴더가 있습니다")
    shutil.move(str(target), str(dst_path))
    str_new_rel = f"{dst_project}/{target.name}"
    await slide_store.rename_folder_in_db(src_path, str_new_rel)
    await _log_management_event(
        request,
        dict_user,
        str_action="project.move_folder",
        str_resource_type="folder",
        str_resource_id=str_new_rel,
        str_detail=f"Moved folder {src_path} to {str_new_rel}",
        dict_extra={"str_src_path": src_path, "str_dst_path": str_new_rel, "str_dst_project": dst_project},
        dict_before={"path": src_path},
        dict_after={"path": str_new_rel},
    )
    return {"status": "moved", "src_path": src_path, "dst_path": str_new_rel}


@router.post("/project/delete", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def delete_project(
    request: Request,
    name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    """빈 프로젝트 삭제."""
    name = _safe_filename(name)
    target = _safe_subpath(name)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    if any(target.iterdir()):
        raise HTTPException(400, "프로젝트가 비어있지 않습니다")
    target.rmdir()
    if is_db_connected():
        db = get_db()
        dict_before = _project_public_info(await db.project_infos.find_one({"str_project_path": name}))
        await db.project_infos.delete_one({"str_project_path": name})
    else:
        dict_before = None
    class_dir = Path(settings.ANNOTATIONS_DIR) / "_projects" / _annotation_slide_dirname(name)
    if class_dir.exists():
        shutil.rmtree(class_dir)
    await _log_management_event(
        request,
        dict_user,
        str_action="project.delete",
        str_resource_type="project",
        str_resource_id=name,
        str_detail=f"Deleted project {name}",
        dict_before=dict_before,
    )
    return {"status": "deleted", "name": name}


@router.post("/folder/create")
async def create_folder(
    request: Request,
    path: str = Form(""),
    name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    """폴더 생성"""
    name = _safe_filename(name)
    target = _safe_subpath(path) / name
    if target.exists():
        raise HTTPException(400, "이미 존재하는 폴더입니다")
    target.mkdir(parents=True, exist_ok=True)
    str_parent = path.replace("\\", "/").strip("/")
    str_new_rel = f"{str_parent}/{name}" if str_parent else name
    await _log_management_event(
        request,
        dict_user,
        str_action="folder.create",
        str_resource_type="folder",
        str_resource_id=str_new_rel,
        str_detail=f"Created folder {str_new_rel}",
        dict_after={"path": str_new_rel},
    )
    return {"status": "created", "path": str_new_rel}


@router.post("/folder/rename")
async def rename_folder(
    request: Request,
    path: str = Form(...),
    new_name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    """폴더 이름 변경"""
    new_name = _safe_filename(new_name)
    target = _safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "폴더를 찾을 수 없습니다")
    new_target = target.parent / new_name
    if new_target.exists():
        raise HTTPException(400, "이미 존재하는 이름입니다")
    target.rename(new_target)

    # DB 에 저장된 하위 슬라이드 문서의 rel_path 갱신
    old_rel = path.replace("\\", "/").strip("/")
    parent_rel = "/".join(old_rel.split("/")[:-1])
    new_rel = f"{parent_rel}/{new_name}" if parent_rel else new_name
    await slide_store.rename_folder_in_db(old_rel, new_rel)
    await _log_management_event(
        request,
        dict_user,
        str_action="folder.rename",
        str_resource_type="folder",
        str_resource_id=new_rel,
        str_detail=f"Renamed folder {old_rel} to {new_rel}",
        dict_extra={"str_old_path": old_rel, "str_new_path": new_rel},
        dict_before={"path": old_rel},
        dict_after={"path": new_rel},
    )
    return {"status": "renamed"}


@router.post("/folder/delete")
async def delete_folder(
    request: Request,
    path: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    """폴더 삭제 (비어있을 때만)"""
    target = _safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "폴더를 찾을 수 없습니다")
    # 비어있는지 확인
    children = list(target.iterdir())
    if children:
        raise HTTPException(400, "폴더가 비어있지 않습니다")
    target.rmdir()
    str_rel = path.replace("\\", "/").strip("/")
    await _log_management_event(
        request,
        dict_user,
        str_action="folder.delete",
        str_resource_type="folder",
        str_resource_id=str_rel,
        str_detail=f"Deleted folder {str_rel}",
        dict_before={"path": str_rel},
    )
    return {"status": "deleted"}


def _cleanup_ai_caches_for_stem(str_stem: str) -> list:
    """주어진 slide stem 에 속한 AI 결과 캐시/타일 피라미드 제거.

    파일/폴더 명명 규칙:
        - ai_results/Quanti HE/{stem}_Quanti HE_*.json
        - ai_results/Quanti PD-L1/{stem}_Quanti PD-L1_*.json
        - ai_results/Quanti IHC/{stem}_Quanti IHC_*.json
        - ai_results/VS IHC/{stem}_VS IHC_*.(png|json)
        - ai_results/VS IHC/{stem}_VS IHC_*_tile/  (피라미드 폴더)
        - ai_results/{stem}_*  (레거시 루트)
    """
    list_removed = []
    try:
        ai_dir = Path(settings.AI_RESULTS_DIR)
    except Exception:
        return list_removed
    if not ai_dir.exists():
        return list_removed
    list_sub_dirs = [ai_dir] + [
        ai_dir / s for s in (
            "Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC",
            "HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC",
        )
    ]
    for d in list_sub_dirs:
        if not d.exists() or not d.is_dir():
            continue
        for p in d.glob(f"{str_stem}_*"):
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
                list_removed.append(str(p))
            except Exception as e:
                print(f"[slides] AI cache cleanup failed ({p}): {e}")
    return list_removed


async def _delete_slide_file(str_path: str, str_filename: str) -> dict:
    """파일 + 타일 디렉토리 + AI 결과 캐시 + DB 문서를 모두 제거.

    열려있는 슬라이드면 먼저 close.
    """
    str_filename = _safe_filename(str_filename)
    target = _safe_subpath(str_path) / str_filename
    if not target.exists():
        raise HTTPException(404, f"파일을 찾을 수 없습니다: {str_filename}")

    # 열려있는 슬라이드는 먼저 닫기
    str_slide_id = hashlib.md5(str_filename.encode()).hexdigest()[:12]
    if slide_manager.get(str_slide_id) is not None:
        try:
            slide_manager.close(str_slide_id)
        except Exception as e:
            print(f"[slides] close before delete failed ({str_filename}): {e}")

    str_stem = Path(str_filename).stem

    # 1) 원본 파일 삭제
    try:
        target.unlink()
    except Exception as e:
        raise HTTPException(500, f"파일 삭제 실패: {e}")

    # 2) 타일 피라미드 폴더 삭제
    try:
        tiles_dir = tile_generator.get_tiles_dir(str_filename)
        if tiles_dir.exists():
            shutil.rmtree(tiles_dir, ignore_errors=True)
    except Exception as e:
        print(f"[slides] tiles dir cleanup failed ({str_filename}): {e}")

    # 3) AI 결과 캐시 + VS 타일 피라미드 삭제
    list_removed_ai = _cleanup_ai_caches_for_stem(str_stem)

    # 4) DB 문서 제거
    try:
        await slide_store.delete_slide(str_path, str_filename)
    except Exception as e:
        print(f"[slides] DB delete failed ({str_filename}): {e}")

    return {"filename": str_filename, "ai_files_removed": len(list_removed_ai)}


@router.post("/file/delete")
async def delete_slide_files(
    request: Request,
    filenames_json: str = Form(...),
    path: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    """슬라이드 파일들 + AI 결과/타일 캐시 + DB 문서 일괄 삭제.

    filenames_json: JSON list (예: ["a.svs","b.ndpi"])
    """
    try:
        list_filenames = json.loads(filenames_json)
        if not isinstance(list_filenames, list):
            raise ValueError("filenames_json must be a JSON list")
    except Exception as e:
        raise HTTPException(400, f"잘못된 filenames_json: {e}")

    list_results = []
    list_errors = []
    for str_fn in list_filenames:
        if not isinstance(str_fn, str) or not str_fn:
            continue
        try:
            dict_res = await _delete_slide_file(path, str_fn)
            list_results.append(dict_res)
        except HTTPException as he:
            list_errors.append({"filename": str_fn, "error": he.detail})
        except Exception as e:
            list_errors.append({"filename": str_fn, "error": str(e)})

    await _log_management_event(
        request,
        dict_user,
        str_action="file.delete",
        str_resource_type="file",
        str_resource_id=path.replace("\\", "/").strip("/"),
        str_detail=f"Deleted {len(list_results)} file(s) from {path or 'root'}",
        dict_extra={
            "str_rel_path": path.replace("\\", "/").strip("/"),
            "list_filenames": [r.get("filename") for r in list_results],
            "list_errors": list_errors,
        },
        dict_before={"filenames": [r.get("filename") for r in list_results], "path": path},
    )
    return {
        "status": "ok",
        "deleted": list_results,
        "errors": list_errors,
    }


@router.post("/file/status")
async def set_file_status(
    request: Request,
    filenames_json: str = Form(...),
    path: str = Form(""),
    status: str = Form(""),
    scope: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    """슬라이드 리뷰 상태 일괄 설정.

    status: "" | "pending" | "in_progress" | "done" | "flagged" | "annotation" | "review" | "termination_in_progress" | "termination"
    """
    str_scope = (scope or "").strip().lower()
    if str_scope not in {"", "ai", "annotation"}:
        raise HTTPException(400, f"Invalid status scope: {scope}")
    if status not in slide_store.SET_SLIDE_STATUSES:
        raise HTTPException(400, f"잘못된 status: {status}")
    try:
        list_filenames = json.loads(filenames_json)
        if not isinstance(list_filenames, list):
            raise ValueError("filenames_json must be a JSON list")
    except Exception as e:
        raise HTTPException(400, f"잘못된 filenames_json: {e}")

    int_updated = 0
    for str_fn in list_filenames:
        if not isinstance(str_fn, str) or not str_fn:
            continue
        try:
            await slide_store.set_slide_status(path, str_fn, status, str_scope)
            int_updated += 1
        except Exception as e:
            print(f"[slides] set_slide_status failed ({str_fn}): {e}")
    await _log_management_event(
        request,
        dict_user,
        str_action="slide.status_update",
        str_resource_type="slide",
        str_resource_id=path.replace("\\", "/").strip("/"),
        str_detail=f"Set {str_scope or 'legacy'} status {status or 'none'} on {int_updated} slide(s)",
        dict_extra={
            "str_rel_path": path.replace("\\", "/").strip("/"),
            "list_filenames": [f for f in list_filenames if isinstance(f, str) and f],
            "str_status": status,
            "str_scope": str_scope,
            "int_updated": int_updated,
        },
        dict_after={"status": status, "scope": str_scope},
    )
    return {"status": "ok", "updated": int_updated}


@router.post("/file/move")
async def move_file(
    request: Request,
    filename: str = Form(...),
    src_path: str = Form(""),
    dst_path: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    """파일을 다른 폴더로 이동"""
    filename = _safe_filename(filename)
    src = _safe_subpath(src_path) / filename
    dst_dir = _safe_subpath(dst_path)
    if not src.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    if not dst_dir.exists() or not dst_dir.is_dir():
        raise HTTPException(404, "대상 폴더를 찾을 수 없습니다")
    dst = dst_dir / filename
    if dst.exists():
        raise HTTPException(400, "대상 폴더에 같은 이름의 파일이 있습니다")
    shutil.move(str(src), str(dst))
    await slide_store.move_slide(src_path, filename, dst_path, str(dst))
    await _log_management_event(
        request,
        dict_user,
        str_action="file.move",
        str_resource_type="file",
        str_resource_id=filename,
        str_detail=f"Moved file {filename} from {src_path or 'root'} to {dst_path or 'root'}",
        dict_extra={"str_filename": filename, "str_src_path": src_path, "str_dst_path": dst_path},
        dict_before={"path": src_path, "filename": filename},
        dict_after={"path": dst_path, "filename": filename},
    )
    return {"status": "moved"}


# ── 서버에 파일 존재 확인 후 바로 열기 ──

@router.post("/open-by-name")
async def open_slide_by_name(
    filename: str = Form(...),
    path: str = Form(""),
):
    """업로드 사전 검사용 — 파일 존재 여부만 반환. 슬라이드 열기/타일 생성/감사 로그 없음."""
    filename = _safe_filename(filename)
    final_path = _safe_subpath(path) / filename
    return {"exists": final_path.exists()}


@router.post("/open")
async def open_slide(
    request: Request,
    filename: str = Form(...),
    path: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    """파일명으로 서버 디스크에 있는지 확인 → 있으면 바로 열기"""
    filename = _safe_filename(filename)
    final_path = _safe_subpath(path) / filename
    if not final_path.exists():
        return {"exists": False}

    slide_id = hashlib.md5(filename.encode()).hexdigest()[:12]
    resp = await _open_and_generate(slide_id, str(final_path), filename, dict_user)
    resp["exists"] = True

    # 슬라이드 조회 감사 로그 — 활동 분석용
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


# ── 청크 업로드 ──

@router.post("/upload/start")
async def upload_start(filename: str = Form(...)):
    """업로드 시작 — upload_id 발급"""
    filename = _safe_filename(filename)
    ext = Path(filename).suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 파일 형식: {ext}")

    upload_id = uuid.uuid4().hex[:12]
    chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    return {
        "upload_id": upload_id,
        "filename": filename,
        "chunk_size": settings.CHUNK_SIZE,
    }


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
):
    """청크 업로드 — 개별 청크 저장. 업로드 카운터로 auto_ai 일시정지."""
    auto_ai.upload_enter()
    try:
        chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
        if not chunk_dir.exists():
            raise HTTPException(404, "업로드 세션을 찾을 수 없습니다")

        chunk_path = chunk_dir / f"chunk_{chunk_index:06d}"
        content = await chunk.read()
        with open(chunk_path, "wb") as f:
            f.write(content)

        return {"chunk_index": chunk_index, "size": len(content)}
    finally:
        auto_ai.upload_exit()


@router.post("/upload/complete")
async def upload_complete(
    request: Request,
    upload_id: str = Form(...),
    filename: str = Form(...),
    total_chunks: int = Form(...),
    path: str = Form(""),
    wait_tiles: str = Form("false"),
    dict_user: dict = Depends(get_current_user),
):
    """업로드 완료 — 청크 조립 → 슬라이드 열기 + 타일 생성"""
    auto_ai.upload_enter()
    try:
        # 파일명 검증을 가장 먼저 — 이후 모든 디스크 경로 join 의 안전 보장
        filename = _safe_filename(filename)

        chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
        if not chunk_dir.exists():
            raise HTTPException(404, "업로드 세션을 찾을 수 없습니다")

        # 확장자 재검증 (start 단계 우회 방지)
        ext = Path(filename).suffix.lower()
        if ext not in settings.SUPPORTED_EXTENSIONS:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            raise HTTPException(400, f"지원하지 않는 파일 형식: {ext}")

        # 청크 총 크기 선집계 → 상한 초과 시 조립 전에 거부
        int_total_bytes = 0
        for i in range(total_chunks):
            chunk_path = chunk_dir / f"chunk_{i:06d}"
            if not chunk_path.exists():
                shutil.rmtree(chunk_dir, ignore_errors=True)
                raise HTTPException(400, f"청크 {i} 누락")
            int_total_bytes += chunk_path.stat().st_size
        if int_total_bytes > settings.MAX_UPLOAD_BYTES:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            int_limit_gb = settings.MAX_UPLOAD_BYTES / (1024 ** 3)
            raise HTTPException(
                413,
                f"업로드 크기 상한 초과: {int_total_bytes / (1024**3):.2f} GB > {int_limit_gb:.2f} GB",
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
        str_sha256 = ""
        if final_path.exists():
            shutil.rmtree(chunk_dir, ignore_errors=True)
        else:
            sha256_hash = hashlib.sha256()
            with open(final_path, "wb") as out:
                for i in range(total_chunks):
                    chunk_path = chunk_dir / f"chunk_{i:06d}"
                    with open(chunk_path, "rb") as cf:
                        while True:
                            bytes_block = cf.read(8192)
                            if not bytes_block:
                                break
                            out.write(bytes_block)
                            sha256_hash.update(bytes_block)
            str_sha256 = sha256_hash.hexdigest()
            shutil.rmtree(chunk_dir, ignore_errors=True)
            bool_newly_written = True

        # 기존 파일의 체크섬도 계산 (DB에 미저장된 경우)
        if not str_sha256 and final_path.exists():
            sha256_hash = hashlib.sha256()
            with open(final_path, "rb") as f:
                while True:
                    bytes_block = f.read(8192)
                    if not bytes_block:
                        break
                    sha256_hash.update(bytes_block)
            str_sha256 = sha256_hash.hexdigest()

        slide_id = hashlib.md5(filename.encode()).hexdigest()[:12]
        bool_wait = wait_tiles.lower() in ("true", "1", "yes")
        try:
            resp = await _open_and_generate(
                slide_id, str(final_path), filename, dict_user,
                bool_wait_for_tiles=bool_wait,
                str_sha256=str_sha256,
            )
            await _log_management_event(
                request,
                dict_user,
                str_action="slide.upload",
                str_resource_type="slide",
                str_resource_id=slide_id,
                str_detail=f"Uploaded slide {filename} to {str_norm_upload_path}",
                dict_extra={
                    "str_filename": filename,
                    "str_rel_path": str_norm_upload_path,
                    "str_project": str_project,
                    "int_size_bytes": int_total_bytes,
                    "str_sha256": str_sha256,
                    "bool_new_file": bool_newly_written,
                },
                dict_after={
                    "filename": filename,
                    "path": str_norm_upload_path,
                    "sha256": str_sha256,
                    "new_file": bool_newly_written,
                },
            )
            return resp
        except HTTPException:
            # OpenSlide 열기 실패 — 손상/위조 파일로 간주, 이번 업로드로 쓴 경우만 정리
            if bool_newly_written and final_path.exists():
                try:
                    final_path.unlink()
                except Exception:
                    pass
            raise
    finally:
        auto_ai.upload_exit()


# ── 서버 로컬 파일 열기 ──

@router.post("/open-local")
async def open_local_file(
    request: Request,
    file_path: str = Form(...),
    dict_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """서버 로컬 디스크의 WSI 파일 열기.

    file_path 는 반드시 UPLOAD_DIR 하위여야 한다 — admin 이라도 /etc/passwd.svs
    같은 임의 경로를 읽지 못하도록 컨테인먼트 강제.
    """
    path = Path(file_path).resolve()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    try:
        path.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(400, "uploads/ 외부 경로는 허용되지 않습니다")
    if not path.exists():
        raise HTTPException(404, f"파일이 존재하지 않습니다: {path.name}")

    ext = path.suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 파일 형식: {ext}")

    slide_id = hashlib.md5(path.name.encode()).hexdigest()[:12]
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


# ── 타일 생성 진행 상태 ──

@router.get("/tile-progress/{slide_id}")
async def get_tile_progress(slide_id: str):
    """타일 프리제네레이션 진행 상태 (slide_id로 filename 조회)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    filename = Path(info.file_path).name
    progress = tile_generator.get_progress(filename)
    if progress is None:
        raise HTTPException(404, "타일 생성 정보를 찾을 수 없습니다")
    return progress


# ── 슬라이드 정보 ──

@router.get("/{slide_id}/info")
async def get_slide_info(slide_id: str):
    """슬라이드 메타데이터 조회"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

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
        "tiles_ready": tile_generator.tiles_ready(Path(info.file_path).name),
    }


@router.get("/{slide_id}/verify-integrity")
async def verify_slide_integrity(slide_id: str, dict_user: dict = Depends(get_current_user)):
    """슬라이드 파일의 SHA-256 체크섬을 재계산하여 DB 저장값과 비교."""
    from app.database import get_db as _get_db

    db = _get_db()
    dict_doc = await db.slides.find_one({"str_slide_id": slide_id})
    if not dict_doc:
        raise HTTPException(404, "슬라이드 DB 레코드 없음")

    str_stored_hash = dict_doc.get("str_sha256", "")
    str_file_path = dict_doc.get("str_full_path", "")
    if not str_file_path or not Path(str_file_path).exists():
        raise HTTPException(404, "슬라이드 파일을 찾을 수 없습니다")

    # 재계산
    sha256_hash = hashlib.sha256()
    with open(str_file_path, "rb") as f:
        while True:
            bytes_block = f.read(8192)
            if not bytes_block:
                break
            sha256_hash.update(bytes_block)
    str_current_hash = sha256_hash.hexdigest()

    bool_match = str_stored_hash == str_current_hash if str_stored_hash else False

    # 저장된 해시가 없으면 이번에 저장
    if not str_stored_hash:
        await db.slides.update_one(
            {"str_slide_id": slide_id},
            {"$set": {"str_sha256": str_current_hash}},
        )

    return {
        "slide_id": slide_id,
        "filename": dict_doc.get("str_filename", ""),
        "str_stored_hash": str_stored_hash or "(not set — saved now)",
        "str_current_hash": str_current_hash,
        "bool_integrity_ok": bool_match if str_stored_hash else True,
    }


@media_router.get("/thumbnail-by-name")
async def get_thumbnail_by_name(
    filename: str = Query(...),
    path: str = Query(""),
    size: int = Query(300, ge=64, le=1024),
):
    """파일명 기반 썸네일 — slide_manager 불필요, 디스크에서 바로 반환"""
    import io
    import openslide

    filename = _safe_filename(filename)
    # 1) 프리제네레이트된 썸네일이 있으면 바로 반환
    thumb_path = tile_generator.get_tiles_dir(filename) / "thumbnail.jpeg"
    if thumb_path.exists():
        return StreamingResponse(open(thumb_path, "rb"), media_type="image/jpeg")

    # 2) 없으면 즉석 생성 + 저장
    file_path = _safe_subpath(path) / filename
    if not file_path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다")

    try:
        from app.slide_manager import build_color_corrector

        slide = openslide.OpenSlide(str(file_path))
        thumb = slide.get_thumbnail((size, size))
        thumb_rgb = thumb.convert("RGB")

        # 통합 색 보정 — ICC → NDP LUT → raw 순. slide_manager 와 동일 로직.
        _apply_color, _ = build_color_corrector(slide)
        thumb_rgb = _apply_color(thumb_rgb)

        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_rgb.save(str(thumb_path), "JPEG", quality=85)
        slide.close()

        buf = io.BytesIO()
        thumb_rgb.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(500, f"썸네일 생성 실패: {e}")


@media_router.get("/{slide_id}/preview")
async def get_preview(
    slide_id: str,
    size: int = Query(2048, ge=512, le=8192),
    ndp: bool = Query(False, description="true 면 NDP 색 매칭 2차 보정 적용"),
):
    """고해상도 슬라이드 프리뷰 (PDF 리포트용, 캐시 미사용)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    import io
    thumb = info.slide.get_thumbnail((size, size))
    thumb_rgb = info.apply_icc(thumb.convert("RGB"))
    if ndp:
        from app.ndp_color_match import apply_ndp_fit
        thumb_rgb = apply_ndp_fit(thumb_rgb)
    buf = io.BytesIO()
    thumb_rgb.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


@media_router.get("/{slide_id}/thumbnail")
async def get_thumbnail(
    slide_id: str,
    size: int = Query(300, ge=64, le=1024),
    ndp: bool = Query(False, description="true 면 NDP 색 매칭 2차 보정본 반환"),
):
    """slide_id 기반 썸네일 (하위 호환). `?ndp=true` 면 ndpmatch 버전."""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    filename = Path(info.file_path).name
    tiles_root = tile_generator.get_tiles_dir(filename)
    thumb_path_raw = tiles_root / "thumbnail.jpeg"
    thumb_path_ndp = tiles_root / "ndpmatch" / "thumbnail.jpeg"

    # NDP 변형 요청 — 있으면 바로, 없으면 raw 썸네일 → apply → 저장
    if ndp:
        if thumb_path_ndp.exists():
            return StreamingResponse(open(thumb_path_ndp, "rb"), media_type="image/jpeg")

        from PIL import Image as _Image
        from app.ndp_color_match import apply_ndp_fit
        # raw 썸네일 확보 (없으면 slide 에서 즉석 생성)
        if thumb_path_raw.exists():
            obj_rgb = _Image.open(str(thumb_path_raw)).convert("RGB")
        else:
            obj_thumb = info.slide.get_thumbnail((size, size))
            obj_rgb = info.apply_icc(obj_thumb.convert("RGB"))
            thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
            obj_rgb.save(str(thumb_path_raw), "JPEG", quality=85)

        obj_ndp = apply_ndp_fit(obj_rgb)
        thumb_path_ndp.parent.mkdir(parents=True, exist_ok=True)
        obj_ndp.save(str(thumb_path_ndp), "JPEG", quality=85)
        import io
        buf = io.BytesIO()
        obj_ndp.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/jpeg")

    # raw 경로
    if thumb_path_raw.exists():
        return StreamingResponse(open(thumb_path_raw, "rb"), media_type="image/jpeg")

    import io
    thumb = info.slide.get_thumbnail((size, size))
    thumb_rgb = info.apply_icc(thumb.convert("RGB"))
    thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
    thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=85)
    buf = io.BytesIO()
    thumb_rgb.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


# ── 목록 / 삭제 ──

@router.get("/")
async def list_slides():
    """열린 슬라이드 목록"""
    return slide_manager.list_slides()


# ═══════════════════════════════════════════════════════
# 폴더별 AI 자동 추론 설정 — folder_ai_configs 컬렉션
# ═══════════════════════════════════════════════════════

from datetime import datetime, timezone
from app.database import get_db, is_db_connected


def _norm_folder_path(str_path: str) -> str:
    if not str_path:
        return ""
    return str_path.replace("\\", "/").strip("/")


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
    """폴더의 AI 자동 추론 설정 조회 — 없으면 기본값 반환."""
    if not is_db_connected():
        return {"path": path, "enabled": False, "tasks": []}
    db = get_db()
    str_norm = _norm_folder_path(path)
    dict_doc = await db.folder_ai_configs.find_one({"str_rel_path": str_norm})
    if not dict_doc:
        dict_doc = await _clone_legacy_folder_config(db, str_norm)
    if not dict_doc:
        return {"path": path, "enabled": False, "tasks": []}
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
    }


@router.post("/folder-config", dependencies=[Depends(require_not_viewer)])
async def save_folder_config(
    request: Request,
    path: str = Form(""),
    enabled: bool = Form(True),
    tasks_json: str = Form("[]"),
    dict_user: dict = Depends(get_current_user),
):
    """폴더의 AI 자동 추론 설정 저장/업서트.

    tasks_json: JSON array — `[{"model": "Quanti HE", "variant": "Stomach"}, ...]`
      model 은 {Quanti HE, Quanti PD-L1, Quanti IHC} 중 하나, variant 는 tissue_type/marker.
    """
    if not is_db_connected():
        raise HTTPException(503, "DB 연결 필요")

    try:
        list_raw = json.loads(tasks_json)
        if not isinstance(list_raw, list):
            raise ValueError("tasks_json must be a JSON array")
    except Exception as e:
        raise HTTPException(400, f"잘못된 tasks_json: {e}")

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
    """폴더의 AI 자동 추론 설정 삭제."""
    if not is_db_connected():
        raise HTTPException(503, "DB 연결 필요")
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
    """슬라이드 닫기"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    slide_manager.close(slide_id)
    return {"status": "closed", "slide_id": slide_id}


# ── Annotation 저장/불러오기 ──

_INT_ANNOTATIONS_MAX_BYTES = 8 * 1024 * 1024  # 8 MB — annotation 한 슬라이드 합 상한
_INT_ANNOTATION_CLASSES_MAX_BYTES = 256 * 1024
_DEFAULT_ANNOTATION_CLASSES = [
    {"id": "default", "name": "Default", "color": [0, 255, 0]},
]


def _annotation_slide_dirname(filename: str) -> str:
    """슬라이드 파일명을 annotations 하위 폴더명으로 안전하게 변환."""
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


def _annotation_path_for_filename(filename: str) -> Path:
    return Path(settings.ANNOTATIONS_DIR) / _annotation_slide_dirname(filename) / "annotations.json"


def _annotation_classes_path_for_project(project_path: str) -> Path:
    str_project = (project_path or "").replace("\\", "/").split("/")[0].strip()
    if not str_project:
        raise HTTPException(400, "Project path is required")
    str_project = _safe_filename(str_project)
    project_dir = _safe_subpath(str_project)
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
    """프로젝트 단위 annotation class palette."""
    class_path = _annotation_classes_path_for_project(path)
    if not class_path.exists():
        return {"classes": list(_DEFAULT_ANNOTATION_CLASSES)}
    with open(class_path, "r", encoding="utf-8") as f:
        try:
            payload = json.loads(f.read())
        except Exception as e:
            raise HTTPException(400, f"Invalid annotation class JSON: {e}")
    classes = payload.get("classes") if isinstance(payload, dict) else payload
    return {"classes": _normalize_annotation_classes(classes)}


@router.post("/annotation-classes", dependencies=[Depends(require_not_viewer)])
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
    except Exception as e:
        raise HTTPException(400, f"Invalid annotation class JSON: {e}")
    classes = _normalize_annotation_classes(payload.get("classes") if isinstance(payload, dict) else payload)
    class_path = _annotation_classes_path_for_project(path)
    class_path.parent.mkdir(parents=True, exist_ok=True)
    with open(class_path, "w", encoding="utf-8") as f:
        json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
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
    """슬라이드별 annotation JSON 저장.

    검증 순서가 중요 — 예전엔 파일 먼저 쓰고 `len(json.loads(...))` 으로 검증했는데
    JSON 깨진 입력이 오면 이미 디스크에 무효 데이터가 박힌 채 500 이 났다.
    이제는 (1) 크기 → (2) JSON 파싱 → (3) list 타입 → 다 통과해야 디스크에 쓴다.
    """
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    # 1) 크기 상한 — Form 자체엔 별도 max_length 가 없어 여기서 검사
    if len(data.encode("utf-8")) > _INT_ANNOTATIONS_MAX_BYTES:
        raise HTTPException(413, f"annotation 데이터 상한 초과 ({_INT_ANNOTATIONS_MAX_BYTES // (1024*1024)} MB)")

    # 2) JSON 유효성 + 3) 최상위가 list 인지
    try:
        list_parsed = json.loads(data)
    except Exception as e:
        raise HTTPException(400, f"잘못된 JSON: {e}")
    if not isinstance(list_parsed, list):
        raise HTTPException(400, "annotation 은 list 형식이어야 합니다")

    filename = Path(info.file_path).name
    ann_path = _annotation_path_for_filename(filename)
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ann_path, "w", encoding="utf-8") as f:
        f.write(data)
    return {"status": "saved", "count": len(list_parsed), "path": str(ann_path)}


@router.get("/{slide_id}/annotations/load", dependencies=[Depends(require_not_viewer)])
async def load_annotations(slide_id: str):
    """슬라이드별 annotation JSON 불러오기"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    filename = Path(info.file_path).name
    ann_path = _annotation_path_for_filename(filename)
    if not ann_path.exists():
        ann_path = tile_generator.get_tiles_dir(filename) / "annotations.json"
    if not ann_path.exists():
        return []
    with open(ann_path, "r", encoding="utf-8") as f:
        return json.loads(f.read())
