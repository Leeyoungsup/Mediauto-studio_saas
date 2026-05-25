"""text DB text — MongoDB `slides` text helper

Claude.md text text (str_/int_/bool_/dict_/list_/dt_ text).

- `slides` text text WSI text text + AI text text text.
- DB text text text helper text no-op (None text) — text text text text text.
- (str_rel_path, str_filename) text unique — text text text text text text.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.database import get_db, is_db_connected, get_main_loop


# AI text text (dict_ai_results text key)
LIST_AI_MODEL_KEYS = ["Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC"]
DICT_LEGACY_AI_MODEL_KEYS = {
    "HE-Fit": "Quanti HE",
    "PD-Score": "Quanti PD-L1",
    "Precise-IHC": "Quanti IHC",
    "VS-IHC": "VS IHC",
}
DICT_CURRENT_TO_LEGACY_AI_MODEL_KEYS = {
    str_current: str_legacy
    for str_legacy, str_current in DICT_LEGACY_AI_MODEL_KEYS.items()
}

# text text text (str_status). "" = none.
SET_SLIDE_STATUSES = {
    "",
    "pending", "in_progress", "done", "flagged",
    "annotation", "review", "termination_in_progress", "termination",
}


def _empty_ai_results() -> dict:
    """dict_ai_results text — text bool/list/dt text."""
    return {
        str_key: {
            "bool_has_result": False,
            "list_variants": [],
            "dt_updated_at": None,
        }
        for str_key in LIST_AI_MODEL_KEYS
    }


def _norm_ai_model_key(str_model: str) -> str:
    return DICT_LEGACY_AI_MODEL_KEYS.get(str_model, str_model)


def _legacy_ai_model_key(str_model: str) -> str:
    return DICT_CURRENT_TO_LEGACY_AI_MODEL_KEYS.get(str_model, "")


def _safe_ai_facet_key(str_model: str) -> str:
    return f"ai_{str_model.replace('-', '_').replace(' ', '_')}"


def _norm_rel_path(str_rel_path: str) -> str:
    """rel_path text — text text text, text → text."""
    if not str_rel_path:
        return ""
    return str_rel_path.replace("\\", "/").strip("/")


def _norm_open_page(str_open_page: str) -> str:
    str_page = (str_open_page or "").strip()
    if str_page in {"ai", "tissue-annotation", "cell-annotation"}:
        return str_page
    if str_page == "annotation":
        return "tissue-annotation"
    return "ai"


async def upsert_slide(
    *,
    str_slide_id: str,
    str_filename: str,
    str_rel_path: str,
    str_full_path: str,
    dict_info: dict,
    int_size_bytes: int,
    str_uploaded_by: str = "",
    str_last_opened_page: str = "ai",
) -> Optional[dict]:
    """text text/text text DB text.

    - text: dict_ai_results text + text text text
    - text: text text/text text + dt_last_opened_at text (ai_results text)
    """
    if not is_db_connected():
        return None

    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    dt_now = datetime.now(timezone.utc)

    dict_set_on_insert = {
        "str_slide_id": str_slide_id,
        "str_filename": str_filename,
        "str_rel_path": str_rel_path,
        "str_uploaded_by": str_uploaded_by,
        "dt_uploaded_at": dt_now,
        "dt_created_at": dt_now,
        "dict_ai_results": _empty_ai_results(),
        "bool_tiles_ready": False,
        "dt_tiles_ready_at": None,
        "str_sha256": "",
    }
    dict_set = {
        "str_full_path": str_full_path,
        "int_size_bytes": int(int_size_bytes),
        "int_width": int(dict_info.get("dimensions", [0, 0])[0]),
        "int_height": int(dict_info.get("dimensions", [0, 0])[1]),
        "float_mpp": float(dict_info.get("mpp") or 0.0),
        "str_vendor": str(dict_info.get("vendor") or ""),
        "float_objective_power": float(dict_info.get("objective_power") or 0.0),
        "dt_last_opened_at": dt_now,
        "str_last_opened_page": _norm_open_page(str_last_opened_page),
        "dt_updated_at": dt_now,
    }

    await db.slides.update_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename},
        {"$set": dict_set, "$setOnInsert": dict_set_on_insert},
        upsert=True,
    )
    return await db.slides.find_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename}
    )


async def touch_last_opened(str_rel_path: str, str_filename: str, str_open_page: str = "ai") -> None:
    """text text text dt_last_opened_at text."""
    if not is_db_connected():
        return
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    await db.slides.update_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename},
        {"$set": {
            "dt_last_opened_at": datetime.now(timezone.utc),
            "str_last_opened_page": _norm_open_page(str_open_page),
        }},
    )


async def mark_ai_result(
    str_rel_path: str,
    str_filename: str,
    str_model: str,
    str_variant: str = "",
) -> None:
    """AI text text text text text — text text text true + variant text.

    str_model: LIST_AI_MODEL_KEYS text text ("Quanti HE"/"Quanti PD-L1"/"Quanti IHC"/"VS IHC")
    str_variant: tissue_type/marker/stain_type text — text text list_variants text text.
    """
    if not is_db_connected():
        return
    str_model = _norm_ai_model_key(str_model)
    if str_model not in LIST_AI_MODEL_KEYS:
        return
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    dt_now = datetime.now(timezone.utc)

    dict_update = {
        "$set": {
            f"dict_ai_results.{str_model}.bool_has_result": True,
            f"dict_ai_results.{str_model}.dt_updated_at": dt_now,
            "dt_updated_at": dt_now,
        }
    }
    if str_variant:
        dict_update["$addToSet"] = {
            f"dict_ai_results.{str_model}.list_variants": str_variant
        }

    try:
        result = await db.slides.update_one(
            {"str_rel_path": str_rel_path, "str_filename": str_filename},
            dict_update,
        )
    except Exception as e:
        # MongoDB write error (text: dict_ai_results.Quanti HE text array text text text text)
        # text text text main loop text unhandled exception text text.
        # text text text text → auto_ai text text text text text text
        # text text text text text text.
        print(f"[slide_store] mark_ai_result update failed "
              f"rel='{str_rel_path}' name='{str_filename}' model={str_model} "
              f"variant={str_variant}: {e!r}")
        return

    if result.matched_count == 0:
        # auto_ai text list_slides_missing_variant text text text mark_ai_result
        # text text path text text text text text text text text text.
        # text rel_path text text text — text text text.
        print(f"[slide_store] mark_ai_result NO MATCH "
              f"rel='{str_rel_path}' name='{str_filename}' model={str_model} "
              f"variant={str_variant} — slide doc not found, AI flag NOT persisted")


def mark_ai_result_threadsafe(
    str_full_slide_path: str,
    str_model: str,
    str_variant: str = "",
) -> None:
    """text text (AI text text) text text sync wrapper.

    `str_full_slide_path` text uploads/ text text text + text text
    text text text `mark_ai_result` text text.
    DB text / text text / text text text text text no-op.
    """
    if not is_db_connected():
        return
    loop = get_main_loop()
    if loop is None or not loop.is_running():
        return

    try:
        from app.config import settings
        p = Path(str_full_slide_path).resolve()
        upload_dir = Path(settings.UPLOAD_DIR).resolve()
        str_rel_path = str(p.parent.relative_to(upload_dir)).replace("\\", "/")
        if str_rel_path in (".", ""):
            str_rel_path = ""
        str_filename = p.name
    except Exception as e:
        print(f"[slide_store] threadsafe path resolve failed: {e}")
        return

    try:
        asyncio.run_coroutine_threadsafe(
            mark_ai_result(str_rel_path, str_filename, str_model, str_variant),
            loop,
        )
    except Exception as e:
        print(f"[slide_store] schedule mark_ai_result failed: {e}")


async def mark_tiles_ready(
    str_rel_path: str,
    str_filename: str,
    bool_ready: bool = True,
) -> None:
    """text text text text text text."""
    if not is_db_connected():
        return
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    dt_now = datetime.now(timezone.utc)
    result = await db.slides.update_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename},
        {"$set": {
            "bool_tiles_ready": bool(bool_ready),
            "dt_tiles_ready_at": dt_now if bool_ready else None,
            "dt_updated_at": dt_now,
        }},
    )
    if result.matched_count == 0:
        print(f"[slide_store] mark_tiles_ready: NO MATCH rel='{str_rel_path}' name='{str_filename}'")


def mark_tiles_ready_threadsafe(str_full_slide_path: str) -> None:
    """tile_generator text text text — text text text text."""
    if not is_db_connected():
        return
    loop = get_main_loop()
    if loop is None or not loop.is_running():
        return
    try:
        from app.config import settings
        p = Path(str_full_slide_path).resolve()
        upload_dir = Path(settings.UPLOAD_DIR).resolve()
        str_rel_path = str(p.parent.relative_to(upload_dir)).replace("\\", "/")
        if str_rel_path in (".", ""):
            str_rel_path = ""
        str_filename = p.name
    except Exception as e:
        print(f"[slide_store] mark_tiles_ready path resolve failed: {e}")
        return
    try:
        asyncio.run_coroutine_threadsafe(
            mark_tiles_ready(str_rel_path, str_filename, True),
            loop,
        )
    except Exception as e:
        print(f"[slide_store] schedule mark_tiles_ready failed: {e}")


async def list_slides_missing_tiles() -> list:
    """text text text text text text text — text text."""
    if not is_db_connected():
        return []
    db = get_db()
    list_out = []
    async for dict_doc in db.slides.find(
        {"bool_tiles_ready": {"$ne": True}}
    ).sort("dt_uploaded_at", 1):
        list_out.append(dict_doc)
    return list_out


async def has_any_pending_tiles() -> bool:
    """text text text text text text text."""
    if not is_db_connected():
        return False
    db = get_db()
    return bool(await db.slides.find_one({"bool_tiles_ready": {"$ne": True}}))


async def delete_slide(str_rel_path: str, str_filename: str) -> None:
    """text text text text DB text text."""
    if not is_db_connected():
        return
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    await db.slides.delete_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename}
    )


async def set_slide_status(
    str_rel_path: str,
    str_filename: str,
    str_status: str,
    str_scope: str = "",
) -> None:
    """text text text text — "" text text text."""
    if not is_db_connected():
        return
    if str_status not in SET_SLIDE_STATUSES:
        return
    str_status_field = "str_status"
    if str_scope == "ai":
        str_status_field = "str_ai_status"
    elif str_scope == "annotation":
        str_status_field = "str_annotation_status"
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    dict_set = {
        str_status_field: str_status,
        "dt_status_updated_at": datetime.now(timezone.utc),
        "dt_updated_at": datetime.now(timezone.utc),
    }
    if str_scope == "annotation":
        dict_set["str_status"] = str_status
    await db.slides.update_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename},
        {"$set": dict_set},
    )


async def move_slide(
    str_src_path: str,
    str_filename: str,
    str_dst_path: str,
    str_new_full_path: str,
) -> None:
    """text text text DB text rel_path / full_path text."""
    if not is_db_connected():
        return
    db = get_db()
    str_src_path = _norm_rel_path(str_src_path)
    str_dst_path = _norm_rel_path(str_dst_path)
    await db.slides.update_one(
        {"str_rel_path": str_src_path, "str_filename": str_filename},
        {
            "$set": {
                "str_rel_path": str_dst_path,
                "str_full_path": str_new_full_path,
                "dt_updated_at": datetime.now(timezone.utc),
            }
        },
    )


async def rename_folder_in_db(str_old_path: str, str_new_path: str) -> None:
    """text text text text text text text text text rel_path text."""
    if not is_db_connected():
        return
    db = get_db()
    str_old_path = _norm_rel_path(str_old_path)
    str_new_path = _norm_rel_path(str_new_path)
    dt_now = datetime.now(timezone.utc)

    # text text + text text text text
    str_child_regex = f"^{re.escape(str_old_path)}/"
    async for dict_doc in db.slides.find({
        "$or": [
            {"str_rel_path": str_old_path},
            {"str_rel_path": {"$regex": str_child_regex}},
        ]
    }):
        str_cur = dict_doc["str_rel_path"]
        str_new_rel = (
            str_new_path if str_cur == str_old_path
            else str_new_path + str_cur[len(str_old_path):]
        )
        await db.slides.update_one(
            {"_id": dict_doc["_id"]},
            {"$set": {"str_rel_path": str_new_rel, "dt_updated_at": dt_now}},
        )

    async for dict_doc in db.folder_ai_configs.find({
        "$or": [
            {"str_rel_path": str_old_path},
            {"str_rel_path": {"$regex": str_child_regex}},
        ]
    }):
        str_cur = dict_doc["str_rel_path"]
        str_new_rel = (
            str_new_path if str_cur == str_old_path
            else str_new_path + str_cur[len(str_old_path):]
        )
        await db.folder_ai_configs.update_one(
            {"_id": dict_doc["_id"]},
            {"$set": {"str_rel_path": str_new_rel, "dt_updated_at": dt_now}},
        )


async def repair_folder_ai_config_paths() -> int:
    """Move legacy folder AI configs to project-prefixed paths when folders moved.

    Project support treats uploads/<project>/... as the new location. If an old
    config still points to "CaseA" but the folder now exists only at
    "Test/CaseA", move that config document so UI and auto AI find it again.
    Ambiguous matches across multiple projects are skipped.
    """
    if not is_db_connected():
        return 0

    from app.config import settings

    db = get_db()
    upload_root = Path(settings.UPLOAD_DIR)
    if not upload_root.exists():
        return 0

    list_projects = [
        p for p in upload_root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and not p.name.startswith("_chunks_")
    ]
    if not list_projects:
        return 0

    int_repaired = 0
    dt_now = datetime.now(timezone.utc)
    async for dict_doc in db.folder_ai_configs.find({}):
        str_old_path = _norm_rel_path(dict_doc.get("str_rel_path", ""))
        if not str_old_path:
            continue
        if (upload_root / str_old_path).exists():
            continue

        list_candidates = []
        for path_project in list_projects:
            path_candidate = path_project / str_old_path
            if path_candidate.exists() and path_candidate.is_dir():
                list_candidates.append(f"{path_project.name}/{str_old_path}")

        if len(list_candidates) != 1:
            continue

        str_new_path = _norm_rel_path(list_candidates[0])
        dict_existing = await db.folder_ai_configs.find_one({"str_rel_path": str_new_path})
        if dict_existing:
            if not dict_existing.get("list_tasks") and dict_doc.get("list_tasks"):
                await db.folder_ai_configs.update_one(
                    {"_id": dict_existing["_id"]},
                    {"$set": {
                        "bool_enabled": bool(dict_doc.get("bool_enabled", False)),
                        "list_tasks": dict_doc.get("list_tasks") or [],
                        "dt_updated_at": dt_now,
                    }},
                )
            await db.folder_ai_configs.delete_one({"_id": dict_doc["_id"]})
        else:
            await db.folder_ai_configs.update_one(
                {"_id": dict_doc["_id"]},
                {"$set": {"str_rel_path": str_new_path, "dt_updated_at": dt_now}},
            )
        int_repaired += 1

    return int_repaired


async def list_slides_in_folder(str_rel_path: str) -> dict:
    """text text text text text text — {filename: doc} text text."""
    if not is_db_connected():
        return {}
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    dict_result = {}
    async for dict_doc in db.slides.find({"str_rel_path": str_rel_path}):
        dict_result[dict_doc["str_filename"]] = dict_doc
    return dict_result


async def list_slides_missing_variant(
    str_rel_path: str,
    str_model: str,
    str_variant: str,
) -> list:
    """text text (model, variant) text text text text DB text text.

    `dict_ai_results.{model}.list_variants` text text variant text text text
    text text auto_ai text text text text text text. VS IHC text DB text target_mpp
    text text text text text "base model text" text text, per-mpp text
    text text text text text text.
    """
    if not is_db_connected():
        return []
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    str_legacy_model = _legacy_ai_model_key(str_model)
    str_field = f"dict_ai_results.{str_model}.list_variants"
    str_legacy_field = f"dict_ai_results.{str_legacy_model}.list_variants"
    dict_query = {
        "str_rel_path": str_rel_path,
        "$and": [
            {str_field: {"$ne": str_variant}},
            {str_legacy_field: {"$ne": str_variant}} if str_legacy_model else {},
        ],
    }
    list_out = []
    async for dict_doc in db.slides.find(dict_query):
        list_out.append(dict_doc)
    return list_out


async def get_slide(str_rel_path: str, str_filename: str) -> Optional[dict]:
    if not is_db_connected():
        return None
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    return await db.slides.find_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename}
    )


# ═══════════════════════════════════════════════════════════════════
# text — text text / AI text text
# ═══════════════════════════════════════════════════════════════════

async def get_recent_slides(int_limit: int = 12) -> list:
    """text text text (dt_last_opened_at text).

    text text text text text text.
    """
    if not is_db_connected():
        return []
    from app.config import settings

    db = get_db()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    list_out = []
    # text text text text text text text text text
    async for dict_doc in db.slides.find(
        {"dt_last_opened_at": {"$ne": None}},
    ).sort("dt_last_opened_at", -1).limit(int_limit * 3):
        file_path = upload_dir / (dict_doc.get("str_rel_path") or "") / dict_doc["str_filename"]
        if not file_path.exists():
            continue
        list_out.append(dict_doc)
        if len(list_out) >= int_limit:
            break
    return list_out


_disk_cache: dict = {}
_disk_cache_ts: float = 0.0
_DISK_CACHE_TTL = 60.0  # 60text text


def _compute_disk_stats_sync() -> dict:
    """text text (text) — text text."""
    from app.config import settings
    import os
    import shutil

    upload_path = Path(settings.UPLOAD_DIR)
    int_folders = 0
    if upload_path.exists():
        for _root, dirs, _files in os.walk(str(upload_path)):
            dirs[:] = [d for d in dirs if not d.startswith("_chunks_") and not d.startswith(".")]
            int_folders += len(dirs)

    int_used = 0
    for str_dir in [settings.UPLOAD_DIR, settings.TILES_DIR, settings.AI_RESULTS_DIR]:
        dir_path = Path(str_dir)
        if dir_path.exists():
            for _root, _dirs, files in os.walk(str(dir_path)):
                for f in files:
                    try:
                        int_used += os.path.getsize(os.path.join(_root, f))
                    except OSError:
                        pass

    int_total = 0
    try:
        usage = shutil.disk_usage(str(upload_path) if upload_path.exists() else "/")
        int_total = usage.total
    except Exception:
        pass

    return {
        "int_folder_count": int_folders,
        "int_storage_used_bytes": int_used,
        "int_storage_total_bytes": int_total,
    }


async def _get_disk_stats_cached() -> dict:
    """text text text + text text text."""
    import asyncio
    import time
    global _disk_cache, _disk_cache_ts

    float_now = time.monotonic()
    if _disk_cache and (float_now - _disk_cache_ts) < _DISK_CACHE_TTL:
        return _disk_cache

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _compute_disk_stats_sync)
    _disk_cache = result
    _disk_cache_ts = float_now
    return result


async def get_dashboard_stats(bool_include_disk: bool = True) -> dict:
    """text text: text text, AI text text, text text, text text."""
    dict_result = {
        "int_total_slides": 0,
        "dict_ai_counts": {},
        "dict_status_counts": {},
        "int_folder_count": 0,
        "int_storage_used_bytes": 0,
        "int_storage_total_bytes": 0,
    }

    # text text — text + text (text text text text)
    if bool_include_disk:
        dict_disk = await _get_disk_stats_cached()
        dict_result.update(dict_disk)

    if not is_db_connected():
        return dict_result

    db = get_db()

    # text aggregation text text text text + text + AItext text text text text
    pipeline = [
        {"$facet": {
            "total": [{"$count": "n"}],
            "by_status": [
                {"$group": {
                    "_id": {"$ifNull": ["$str_status", ""]},
                    "n": {"$sum": 1},
                }},
            ],
            **{
                _safe_ai_facet_key(str_k): [
                    {"$match": {"$or": [
                        {f"dict_ai_results.{str_k}.bool_has_result": True},
                        {f"dict_ai_results.{_legacy_ai_model_key(str_k)}.bool_has_result": True},
                    ]}},
                    {"$count": "n"},
                ]
                for str_k in LIST_AI_MODEL_KEYS
            },
        }},
    ]
    cursor = db.slides.aggregate(pipeline)
    dict_facet = await cursor.to_list(length=1)
    if dict_facet:
        facet = dict_facet[0]
        # text text text
        total_list = facet.get("total", [])
        dict_result["int_total_slides"] = total_list[0]["n"] if total_list else 0

        # text text
        for doc in facet.get("by_status", []):
            str_s = doc["_id"]
            if str_s == "" or str_s is None:
                dict_result["dict_status_counts"]["none"] = doc["n"]
            else:
                dict_result["dict_status_counts"][str_s] = doc["n"]

        # AI text text
        for str_k in LIST_AI_MODEL_KEYS:
            safe_key = _safe_ai_facet_key(str_k)
            ai_list = facet.get(safe_key, [])
            dict_result["dict_ai_counts"][str_k] = ai_list[0]["n"] if ai_list else 0

    return dict_result


# ═══════════════════════════════════════════════════════════════════
# user_ai_edits — text text text (text text text text)
# ═══════════════════════════════════════════════════════════════════

async def upsert_user_ai_edit(
    *,
    str_slide_id: str,
    str_ai_mode: str,
    str_variant: str,
    str_user_id: str,
    str_user_name: str,
    str_login_id: str,
    str_file_path: str,
    int_total_cells: int,
) -> None:
    """text text text text **text** text `user_ai_edits` text upsert (text text).

    text text text JSON text text(str_file_path) text text, text text/text text text/
    text/text DB text text.
    """
    if not is_db_connected():
        return
    str_ai_mode = _norm_ai_model_key(str_ai_mode)
    if str_ai_mode not in LIST_AI_MODEL_KEYS:
        return
    db = get_db()
    dt_now = datetime.now(timezone.utc)
    dict_filter = {
        "str_slide_id": str_slide_id,
        "str_ai_mode": str_ai_mode,
        "str_variant": str_variant or "",
        "str_user_id": str_user_id,
    }
    dict_set = {
        "str_user_name": str_user_name or "",
        "str_login_id": str_login_id or "",
        "str_file_path": str_file_path,
        "int_total_cells": int(int_total_cells or 0),
        "dt_updated_at": dt_now,
    }
    await db.user_ai_edits.update_one(
        dict_filter,
        {
            "$set": dict_set,
            "$setOnInsert": {"dt_created_at": dt_now, **dict_filter},
        },
        upsert=True,
    )


def _get_visible_cell_count_from_saved_result(str_file_path: str, int_fallback: int) -> int:
    if not str_file_path:
        return int_fallback
    try:
        path_result = Path(str_file_path)
        if not path_result.exists():
            return int_fallback
        with open(path_result, "r", encoding="utf-8") as file_result:
            dict_result = json.load(file_result)
        if isinstance(dict_result, dict) and isinstance(dict_result.get("cells"), list):
            return len(dict_result["cells"])
    except Exception as exc:
        print(f"[user_ai_edits] visible cell count sync failed: {exc}")
    return int_fallback


async def list_user_ai_edits(
    str_slide_id: str,
    str_ai_mode: str,
    str_variant: str,
) -> list:
    """text text+text+variant text text text text text text."""
    if not is_db_connected():
        return []
    str_ai_mode = _norm_ai_model_key(str_ai_mode)
    str_legacy_mode = _legacy_ai_model_key(str_ai_mode)
    db = get_db()
    list_out = []
    dict_query = {
        "str_slide_id": str_slide_id,
        "str_ai_mode": {"$in": [m for m in (str_ai_mode, str_legacy_mode) if m]},
        "str_variant": str_variant or "",
    }
    async for dict_doc in db.user_ai_edits.find(
        dict_query,
    ).sort("dt_updated_at", -1):
        int_stored_cells = int(dict_doc.get("int_total_cells", 0) or 0)
        int_visible_cells = _get_visible_cell_count_from_saved_result(
            dict_doc.get("str_file_path", ""),
            int_stored_cells,
        )
        if int_visible_cells != int_stored_cells:
            await db.user_ai_edits.update_one(
                {"_id": dict_doc["_id"]},
                {"$set": {"int_total_cells": int_visible_cells}},
            )
        list_out.append({
            "str_user_id": dict_doc.get("str_user_id", ""),
            "str_user_name": dict_doc.get("str_user_name", ""),
            "str_login_id": dict_doc.get("str_login_id", ""),
            "int_total_cells": int_visible_cells,
            "dt_updated_at": (
                dict_doc["dt_updated_at"].isoformat()
                if dict_doc.get("dt_updated_at") else None
            ),
        })
    return list_out


async def delete_user_ai_edit(
    str_slide_id: str,
    str_ai_mode: str,
    str_variant: str,
    str_user_id: str,
) -> Optional[dict]:
    """text text text text. text text(text str_file_path) text — text text text."""
    if not is_db_connected():
        return None
    str_ai_mode = _norm_ai_model_key(str_ai_mode)
    str_legacy_mode = _legacy_ai_model_key(str_ai_mode)
    db = get_db()
    return await db.user_ai_edits.find_one_and_delete({
        "str_slide_id": str_slide_id,
        "str_ai_mode": {"$in": [m for m in (str_ai_mode, str_legacy_mode) if m]},
        "str_variant": str_variant or "",
        "str_user_id": str_user_id,
    })


async def get_user_ai_edit(
    str_slide_id: str,
    str_ai_mode: str,
    str_variant: str,
    str_user_id: str,
) -> Optional[dict]:
    """text text text text text."""
    if not is_db_connected():
        return None
    str_ai_mode = _norm_ai_model_key(str_ai_mode)
    str_legacy_mode = _legacy_ai_model_key(str_ai_mode)
    db = get_db()
    return await db.user_ai_edits.find_one({
        "str_slide_id": str_slide_id,
        "str_ai_mode": {"$in": [m for m in (str_ai_mode, str_legacy_mode) if m]},
        "str_variant": str_variant or "",
        "str_user_id": str_user_id,
    })


def serialize_slide_doc(dict_doc: dict) -> dict:
    """MongoDB text → JSON-friendly dict (ObjectId/datetime text)."""
    if not dict_doc:
        return {}
    dict_out = {}
    for str_key, obj_val in dict_doc.items():
        if str_key == "_id":
            dict_out[str_key] = str(obj_val)
        elif isinstance(obj_val, datetime):
            dict_out[str_key] = obj_val.isoformat()
        elif isinstance(obj_val, dict):
            dict_out[str_key] = {
                str_k: (v.isoformat() if isinstance(v, datetime) else
                        {str_kk: (vv.isoformat() if isinstance(vv, datetime) else vv)
                         for str_kk, vv in v.items()} if isinstance(v, dict) else v)
                for str_k, v in obj_val.items()
            }
        else:
            dict_out[str_key] = obj_val
    return dict_out
