"""text AI text text/text/text text.

routers/ai.py text text text text text.
text text(get_current_user, require_not_viewer) text text text text.

text text:
- text: AI_RESULTS_DIR/user_edits/{user_id}/{ai_mode}/{slide_cache_key}_{variant}.json
- DB: slide_store text user_ai_edits text (text — text/text text/text)
text text text(ai_results/...) text text text text.
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app.activity_audit import audit_activity
from app.auth import get_current_user
from app.config import settings
from app.models import UserRole
from app.slide_identity import slide_cache_key
from app.slide_manager import slide_manager

router = APIRouter()

_USER_EDIT_MODES = {"Quanti HE", "Quanti PD-L1", "Quanti IHC"}
_LEGACY_USER_EDIT_MODES = {
    "HE-Fit": "Quanti HE",
    "PD-Score": "Quanti PD-L1",
    "Precise-IHC": "Quanti IHC",
}


def _normalize_ai_mode(ai_mode: str) -> str:
    return _LEGACY_USER_EDIT_MODES.get(ai_mode, ai_mode)


def _reject_labeler_ai_edit(dict_user: dict):
    if dict_user.get("str_role") == UserRole.LABELER.value:
        raise HTTPException(403, "Labeler role cannot save or load AI edits")


def _get_user_edit_path(slide_path: str, ai_mode: str, variant: str, user_id: str) -> Path:
    """text text JSON text text:
       AI_RESULTS_DIR/user_edits/{user_id}/{ai_mode}/{slide_cache_key}_{variant}.json
    """
    safe_user = "".join(c for c in (user_id or "anon") if c.isalnum() or c in "-_")
    safe_variant = "".join(c for c in (variant or "default") if c.isalnum() or c in "-_")
    base_dir = Path(settings.AI_RESULTS_DIR) / "user_edits" / safe_user / ai_mode
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{slide_cache_key(slide_path)}_{safe_variant}.json"


@router.post("/save-result")
@audit_activity("ai.annotation_save")
async def save_detection_result(
    request: Request,
    slide_id: str = Form(...),
    tissue_type: str = Form("Stomach"),
    result: str = Form(...),
    ai_mode: str = Form("Quanti HE"),
    dict_user: dict = Depends(get_current_user),
):
    """
    text text **text text text text**text DB text text.
    text text text (ai_results/...) text text text.
    """
    _reject_labeler_ai_edit(dict_user)
    ai_mode = _normalize_ai_mode(ai_mode)
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"text text AI text: {ai_mode}")

    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")

    # text AI text(text~text MB) — JSON text/text text text
    # text text text text text text text text text text.
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
        raise HTTPException(401, "text text text")

    # 1) text text JSON text (text)
    file_path = _get_user_edit_path(info.file_path, ai_mode, tissue_type or "", str_user_id)
    list_visible_cells = result_obj.get("cells") if isinstance(result_obj, dict) else None
    int_total_cells = (
        len(list_visible_cells)
        if isinstance(list_visible_cells, list)
        else int(result_obj.get("total_cells", 0) or 0)
    )
    if isinstance(result_obj, dict):
        result_obj["total_cells"] = int_total_cells

    def _write_json_to_disk():
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result_obj, f)

    try:
        await loop.run_in_executor(None, _write_json_to_disk)
    except Exception as e:
        print(f"[ai/save-result] disk write failed: {e}")
        raise HTTPException(500, f"Save failed (disk): {e}")

    # 2) DB text text text (text/text/text text/text)
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
    dict_user: dict = Depends(get_current_user),
):
    """text text+text+variant text text text text text text."""
    _reject_labeler_ai_edit(dict_user)
    ai_mode = _normalize_ai_mode(ai_mode)
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"text text AI text: {ai_mode}")
    from app import slide_store
    list_users = await slide_store.list_user_ai_edits(slide_id, ai_mode, variant)
    return {"users": list_users}


@router.delete("/user-edits")
@audit_activity("ai.annotation_delete")
async def delete_user_edit(
    request: Request,
    slide_id: str,
    ai_mode: str,
    variant: str = "",
    dict_user: dict = Depends(get_current_user),
):
    """text text **text** text text text (text text text text)."""
    _reject_labeler_ai_edit(dict_user)
    ai_mode = _normalize_ai_mode(ai_mode)
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"text text AI text: {ai_mode}")
    str_user_id = str(dict_user.get("_id") or "")
    if not str_user_id:
        raise HTTPException(401, "text text text")
    from app import slide_store
    dict_doc = await slide_store.delete_user_ai_edit(
        slide_id, ai_mode, variant, str_user_id,
    )
    if not dict_doc:
        raise HTTPException(404, "text text")
    # text text text
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
    dict_user: dict = Depends(get_current_user),
):
    """text text text text text — DB text text text text text JSON text."""
    _reject_labeler_ai_edit(dict_user)
    ai_mode = _normalize_ai_mode(ai_mode)
    if ai_mode not in _USER_EDIT_MODES:
        raise HTTPException(400, f"text text AI text: {ai_mode}")
    from app import slide_store
    dict_doc = await slide_store.get_user_ai_edit(slide_id, ai_mode, variant, user_id)
    if not dict_doc:
        raise HTTPException(404, "text text")

    str_file_path = dict_doc.get("str_file_path") or ""
    if not str_file_path or not Path(str_file_path).exists():
        raise HTTPException(404, "text text text")

    # text AI text JSON — text text text text text text.
    # text MB text text text text text.
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
