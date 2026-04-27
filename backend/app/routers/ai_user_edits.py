"""사용자별 AI 편집본 저장/조회/삭제 라우트.

routers/ai.py 의 모놀리스에서 분리된 서브 라우터.
인증 의존성(get_current_user, require_not_viewer) 은 부모 라우터에서 상속.

저장 모델:
- 디스크: AI_RESULTS_DIR/user_edits/{user_id}/{ai_mode}/{slide_stem}_{variant}.json
- DB: slide_store 의 user_ai_edits 컬렉션 (메타만 — 경로/셀 수/시간)
원본 디스크 캐시(ai_results/...) 는 절대 건드리지 않는다.
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException

from app.auth import get_current_user
from app.config import settings
from app.slide_manager import slide_manager

router = APIRouter()

_USER_EDIT_MODES = {"HE-Fit", "PD-Score", "Precise-IHC"}


def _get_user_edit_path(slide_path: str, ai_mode: str, variant: str, user_id: str) -> Path:
    """사용자별 편집본 JSON 저장 경로:
       AI_RESULTS_DIR/user_edits/{user_id}/{ai_mode}/{slide_stem}_{variant}.json
    """
    safe_user = "".join(c for c in (user_id or "anon") if c.isalnum() or c in "-_")
    safe_variant = "".join(c for c in (variant or "default") if c.isalnum() or c in "-_")
    base_dir = Path(settings.AI_RESULTS_DIR) / "user_edits" / safe_user / ai_mode
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(slide_path).stem
    return base_dir / f"{stem}_{safe_variant}.json"


@router.post("/save-result")
async def save_detection_result(
    slide_id: str = Form(...),
    tissue_type: str = Form("Stomach"),
    result: str = Form(...),
    ai_mode: str = Form("HE-Fit"),
    dict_user: dict = Depends(get_current_user),
):
    """
    세포 편집본을 **현재 로그인한 사용자 전용**으로 DB 에 저장한다.
    원본 디스크 캐시 (ai_results/...) 는 건드리지 않는다.
    """
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"지원하지 않는 AI 모드: {ai_mode}")

    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    # 대용량 AI 결과(수십~수백 MB) — JSON 파싱/쓰기를 스레드풀로 오프로드해
    # 이벤트 루프가 타일 서빙 등 다른 요청을 블로킹하지 않게 한다.
    loop = asyncio.get_running_loop()
    try:
        result_obj = await loop.run_in_executor(None, json.loads, result)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    from app import slide_store
    str_user_id = str(dict_user.get("_id") or "")
    str_user_name = str(dict_user.get("str_name") or "")
    str_login_id = str(dict_user.get("str_login_id") or "")
    if not str_user_id:
        raise HTTPException(401, "사용자 식별 실패")

    # 1) 디스크에 사용자별 JSON 저장 (스레드풀에서)
    file_path = _get_user_edit_path(info.file_path, ai_mode, tissue_type or "", str_user_id)

    def _write_json_to_disk():
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result_obj, f)

    try:
        await loop.run_in_executor(None, _write_json_to_disk)
    except Exception as e:
        print(f"[ai/save-result] disk write failed: {e}")
        raise HTTPException(500, f"Save failed (disk): {e}")

    # 2) DB 에는 메타만 기록 (유무/경로/셀 수/시간)
    int_total_cells = int(result_obj.get("total_cells", 0) or 0)
    try:
        await slide_store.upsert_user_ai_edit(
            str_slide_id=slide_id,
            str_ai_mode=ai_mode,
            str_variant=tissue_type or "",
            str_user_id=str_user_id,
            str_user_name=str_user_name,
            str_login_id=str_login_id,
            str_file_path=str(file_path),
            int_total_cells=int_total_cells,
        )
        print(f"[ai/save-result] saved slide={slide_id} mode={ai_mode} "
              f"variant={tissue_type} user={str_user_name or str_login_id} "
              f"cells={int_total_cells} path={file_path}")
    except Exception as e:
        print(f"[ai/save-result] meta upsert failed: {e}")
        raise HTTPException(500, f"Save failed (meta): {e}")

    return {
        "saved": True,
        "ai_mode": ai_mode,
        "variant": tissue_type or "",
        "user_id": str_user_id,
        "user_name": str_user_name,
        "filename": file_path.name,
        "total_cells": int_total_cells,
    }


@router.get("/user-edits/list")
async def list_user_edits(
    slide_id: str,
    ai_mode: str,
    variant: str = "",
):
    """해당 슬라이드+모드+variant 에 대해 저장본을 가진 사용자 목록."""
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"지원하지 않는 AI 모드: {ai_mode}")
    from app import slide_store
    list_users = await slide_store.list_user_ai_edits(slide_id, ai_mode, variant)
    return {"users": list_users}


@router.delete("/user-edits")
async def delete_user_edit(
    slide_id: str,
    ai_mode: str,
    variant: str = "",
    dict_user: dict = Depends(get_current_user),
):
    """현재 로그인한 **본인** 의 편집본만 삭제 (타인 것은 절대 불가)."""
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"지원하지 않는 AI 모드: {ai_mode}")
    str_user_id = str(dict_user.get("_id") or "")
    if not str_user_id:
        raise HTTPException(401, "사용자 식별 실패")
    from app import slide_store
    dict_doc = await slide_store.delete_user_ai_edit(
        slide_id, ai_mode, variant, str_user_id,
    )
    if not dict_doc:
        raise HTTPException(404, "저장본이 없습니다")
    # 디스크 파일도 제거
    str_file_path = dict_doc.get("str_file_path") or ""
    if str_file_path:
        try:
            Path(str_file_path).unlink(missing_ok=True)
        except Exception as e:
            print(f"[ai/user-edits delete] file unlink failed: {e}")
    print(f"[ai/user-edits] deleted slide={slide_id} mode={ai_mode} "
          f"variant={variant} user={str_user_id}")
    return {"deleted": True}


@router.get("/user-edits/load")
async def load_user_edit(
    slide_id: str,
    ai_mode: str,
    user_id: str,
    variant: str = "",
):
    """특정 사용자의 저장본 전체 결과 — DB 메타에서 경로 조회 후 디스크 JSON 반환."""
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"지원하지 않는 AI 모드: {ai_mode}")
    from app import slide_store
    dict_doc = await slide_store.get_user_ai_edit(slide_id, ai_mode, variant, user_id)
    if not dict_doc:
        raise HTTPException(404, "저장본이 없습니다")

    str_file_path = dict_doc.get("str_file_path") or ""
    if not str_file_path or not Path(str_file_path).exists():
        raise HTTPException(404, "저장 파일이 누락되었습니다")

    # 대용량 AI 결과 JSON — 스레드풀로 오프로드해 이벤트 루프 블로킹 방지.
    # 수백 MB 결과도 타일 서빙과 병렬로 처리된다.
    def _read_json_from_disk():
        with open(str_file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    loop = asyncio.get_running_loop()
    try:
        result_obj = await loop.run_in_executor(None, _read_json_from_disk)
    except Exception as e:
        raise HTTPException(500, f"Load failed: {e}")

    return {
        "ai_mode": ai_mode,
        "variant": variant or "",
        "user_id": user_id,
        "user_name": dict_doc.get("str_user_name", ""),
        "result": result_obj,
    }
