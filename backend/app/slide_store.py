"""슬라이드 DB 관리 — MongoDB `slides` 컬렉션 helper

Claude.md 규칙 준수 (str_/int_/bool_/dict_/list_/dt_ 접두어).

- `slides` 컬렉션은 업로드된 WSI 파일의 메타데이터 + AI 결과 플래그를 저장.
- DB 미연결 시 모든 helper 는 no-op (None 리턴) — 파일 시스템 기반 동작은 유지.
- (str_rel_path, str_filename) 쌍이 unique — 같은 폴더에 같은 파일명 중복 금지.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.database import get_db, is_db_connected, get_main_loop


# AI 모델 종류 (dict_ai_results 의 key)
LIST_AI_MODEL_KEYS = ["HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC"]

# 슬라이드 리뷰 상태 (str_status). "" = none.
SET_SLIDE_STATUSES = {"", "pending", "in_progress", "done", "flagged"}


def _empty_ai_results() -> dict:
    """dict_ai_results 기본값 — 모델별 bool/list/dt 플레이스홀더."""
    return {
        str_key: {
            "bool_has_result": False,
            "list_variants": [],
            "dt_updated_at": None,
        }
        for str_key in LIST_AI_MODEL_KEYS
    }


def _norm_rel_path(str_rel_path: str) -> str:
    """rel_path 정규화 — 앞뒤 슬래시 제거, 역슬래시 → 슬래시."""
    if not str_rel_path:
        return ""
    return str_rel_path.replace("\\", "/").strip("/")


async def upsert_slide(
    *,
    str_slide_id: str,
    str_filename: str,
    str_rel_path: str,
    str_full_path: str,
    dict_info: dict,
    int_size_bytes: int,
    str_uploaded_by: str = "",
) -> Optional[dict]:
    """슬라이드 업로드/열기 시 DB 업서트.

    - 신규: dict_ai_results 기본값 + 업로드 정보 세팅
    - 기존: 파일 경로/메타 갱신 + dt_last_opened_at 터치 (ai_results 유지)
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


async def touch_last_opened(str_rel_path: str, str_filename: str) -> None:
    """슬라이드 열기 시 dt_last_opened_at 갱신."""
    if not is_db_connected():
        return
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    await db.slides.update_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename},
        {"$set": {"dt_last_opened_at": datetime.now(timezone.utc)}},
    )


async def mark_ai_result(
    str_rel_path: str,
    str_filename: str,
    str_model: str,
    str_variant: str = "",
) -> None:
    """AI 결과 캐시 생성 직후 호출 — 해당 모델 플래그 true + variant 추가.

    str_model: LIST_AI_MODEL_KEYS 중 하나 ("HE-Fit"/"PD-Score"/"Precise-IHC"/"VS-IHC")
    str_variant: tissue_type/marker/stain_type 등 — 중복 없이 list_variants 에 추가.
    """
    if not is_db_connected():
        return
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
        # MongoDB write error (예: dict_ai_results.HE-Fit 가 array 가 아니라 다른 타입)
        # 가 코루틴에서 발생하면 main loop 의 unhandled exception 으로 묻혀버린다.
        # 여기서 잡아 명시적으로 출력 → auto_ai 가 같은 슬라이드를 매 사이클 다시
        # 추론하는 원인을 즉시 알 수 있다.
        print(f"[slide_store] mark_ai_result update failed "
              f"rel='{str_rel_path}' name='{str_filename}' model={str_model} "
              f"variant={str_variant}: {e!r}")
        return

    if result.matched_count == 0:
        # auto_ai 가 list_slides_missing_variant 로 슬라이드를 찾았는데 mark_ai_result
        # 의 동일 path 검색이 매칭되지 않으면 다음 사이클에서 같은 슬라이드를 또 추론한다.
        # 보통 rel_path 정규화 차이 때문 — 진단 위해 출력.
        print(f"[slide_store] mark_ai_result NO MATCH "
              f"rel='{str_rel_path}' name='{str_filename}' model={str_model} "
              f"variant={str_variant} — slide doc not found, AI flag NOT persisted")


def mark_ai_result_threadsafe(
    str_full_slide_path: str,
    str_model: str,
    str_variant: str = "",
) -> None:
    """백그라운드 스레드 (AI 추론 워커) 에서 호출하는 sync wrapper.

    `str_full_slide_path` 로부터 uploads/ 기준 상대 경로 + 파일명을 계산해
    메인 이벤트 루프에 `mark_ai_result` 코루틴을 스케줄링한다.
    DB 미연결 / 루프 없음 / 경로 계산 실패 시 조용히 no-op.
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
    """뷰어 타일 생성 완료 플래그 설정."""
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
    """tile_generator 백그라운드 스레드에서 호출 — 메인 이벤트 루프에 스케줄."""
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
    """뷰어 타일이 아직 준비 안 된 슬라이드 — 오래된 업로드부터."""
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
    """타일 생성이 끝나지 않은 슬라이드가 하나라도 있는지."""
    if not is_db_connected():
        return False
    db = get_db()
    return bool(await db.slides.find_one({"bool_tiles_ready": {"$ne": True}}))


async def delete_slide(str_rel_path: str, str_filename: str) -> None:
    """슬라이드 파일 삭제 시 DB 문서 제거."""
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
) -> None:
    """슬라이드 리뷰 상태 설정 — "" 는 상태 제거."""
    if not is_db_connected():
        return
    if str_status not in SET_SLIDE_STATUSES:
        return
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    await db.slides.update_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename},
        {"$set": {
            "str_status": str_status,
            "dt_status_updated_at": datetime.now(timezone.utc),
            "dt_updated_at": datetime.now(timezone.utc),
        }},
    )


async def move_slide(
    str_src_path: str,
    str_filename: str,
    str_dst_path: str,
    str_new_full_path: str,
) -> None:
    """파일 이동 시 DB 의 rel_path / full_path 갱신."""
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
    """폴더 이름 변경 시 해당 폴더 아래의 모든 슬라이드의 rel_path 재작성."""
    if not is_db_connected():
        return
    db = get_db()
    str_old_path = _norm_rel_path(str_old_path)
    str_new_path = _norm_rel_path(str_new_path)
    dt_now = datetime.now(timezone.utc)

    # 정확 일치 + 하위 경로 모두 변경
    async for dict_doc in db.slides.find({
        "$or": [
            {"str_rel_path": str_old_path},
            {"str_rel_path": {"$regex": f"^{str_old_path}/"}},
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


async def list_slides_in_folder(str_rel_path: str) -> dict:
    """특정 폴더 내 모든 슬라이드 문서 — {filename: doc} 딕셔너리로 반환."""
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
    """폴더 내에서 (model, variant) 결과가 아직 없는 슬라이드만 DB 질의로 반환.

    `dict_ai_results.{model}.list_variants` 배열에 해당 variant 가 없는 도큐먼트만
    골라 오므로 auto_ai 가 폴더 전체를 순회할 필요가 없다. VS-IHC 는 DB 에 target_mpp
    를 기록하지 않으므로 이 함수로는 "base model 단계" 필터링만 하고, per-mpp 캐시
    존재 확인은 호출자가 따로 수행해야 한다.
    """
    if not is_db_connected():
        return []
    db = get_db()
    str_rel_path = _norm_rel_path(str_rel_path)
    str_field = f"dict_ai_results.{str_model}.list_variants"
    dict_query = {
        "str_rel_path": str_rel_path,
        str_field: {"$ne": str_variant},
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
# 대시보드 — 최근 슬라이드 / AI 통계 집계
# ═══════════════════════════════════════════════════════════════════

async def get_recent_slides(int_limit: int = 12) -> list:
    """최근 열어본 슬라이드 (dt_last_opened_at 내림차순).

    실제 파일이 디스크에 존재하는 슬라이드만 반환.
    """
    if not is_db_connected():
        return []
    from app.config import settings

    db = get_db()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    list_out = []
    # 삭제된 파일이 섞여 있을 수 있으므로 여유 있게 조회
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
_DISK_CACHE_TTL = 60.0  # 60초 캐시


def _compute_disk_stats_sync() -> dict:
    """디스크 통계 (동기) — 스레드풀에서 실행."""
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
    """디스크 통계를 캐시 + 스레드풀로 논블로킹 제공."""
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


async def get_dashboard_stats() -> dict:
    """대시보드 통계: 슬라이드 수, AI 결과 수, 폴더 수, 디스크 사용량."""
    dict_result = {
        "int_total_slides": 0,
        "dict_ai_counts": {},
        "dict_status_counts": {},
        "int_folder_count": 0,
        "int_storage_used_bytes": 0,
        "int_storage_total_bytes": 0,
    }

    # 디스크 통계 — 캐시 + 스레드풀 (이벤트 루프 블로킹 방지)
    dict_disk = await _get_disk_stats_cached()
    dict_result.update(dict_disk)

    if not is_db_connected():
        return dict_result

    db = get_db()

    # 단일 aggregation 파이프라인으로 총 슬라이드 수 + 상태별 + AI별 카운트 한 번에 조회
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
                f"ai_{str_k.replace('-', '_')}": [
                    {"$match": {f"dict_ai_results.{str_k}.bool_has_result": True}},
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
        # 총 슬라이드 수
        total_list = facet.get("total", [])
        dict_result["int_total_slides"] = total_list[0]["n"] if total_list else 0

        # 상태별 카운트
        for doc in facet.get("by_status", []):
            str_s = doc["_id"]
            if str_s == "" or str_s is None:
                dict_result["dict_status_counts"]["none"] = doc["n"]
            else:
                dict_result["dict_status_counts"][str_s] = doc["n"]

        # AI 모델별 카운트
        for str_k in LIST_AI_MODEL_KEYS:
            safe_key = f"ai_{str_k.replace('-', '_')}"
            ai_list = facet.get(safe_key, [])
            dict_result["dict_ai_counts"][str_k] = ai_list[0]["n"] if ai_list else 0

    return dict_result


# ═══════════════════════════════════════════════════════════════════
# user_ai_edits — 사용자별 세포 편집본 (원본 추론 캐시는 유지)
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
    """현재 로그인한 사용자의 편집본 **메타** 를 `user_ai_edits` 에 upsert (최신본만 유지).

    실제 셀 결과 JSON 은 디스크(str_file_path) 에 저장되고, 여기서는 경로/총 셀 수/
    사용자/시각만 DB 에 기록한다.
    """
    if not is_db_connected():
        return
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


async def list_user_ai_edits(
    str_slide_id: str,
    str_ai_mode: str,
    str_variant: str,
) -> list:
    """특정 슬라이드+모드+variant 에 대해 저장본을 가진 사용자 목록."""
    if not is_db_connected():
        return []
    db = get_db()
    list_out = []
    dict_query = {
        "str_slide_id": str_slide_id,
        "str_ai_mode": str_ai_mode,
        "str_variant": str_variant or "",
    }
    async for dict_doc in db.user_ai_edits.find(
        dict_query,
    ).sort("dt_updated_at", -1):
        list_out.append({
            "str_user_id": dict_doc.get("str_user_id", ""),
            "str_user_name": dict_doc.get("str_user_name", ""),
            "str_login_id": dict_doc.get("str_login_id", ""),
            "int_total_cells": int(dict_doc.get("int_total_cells", 0) or 0),
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
    """사용자 편집본 메타 삭제. 삭제된 문서(특히 str_file_path) 반환 — 호출자가 파일도 지움."""
    if not is_db_connected():
        return None
    db = get_db()
    return await db.user_ai_edits.find_one_and_delete({
        "str_slide_id": str_slide_id,
        "str_ai_mode": str_ai_mode,
        "str_variant": str_variant or "",
        "str_user_id": str_user_id,
    })


async def get_user_ai_edit(
    str_slide_id: str,
    str_ai_mode: str,
    str_variant: str,
    str_user_id: str,
) -> Optional[dict]:
    """특정 사용자의 편집본 전체 결과."""
    if not is_db_connected():
        return None
    db = get_db()
    return await db.user_ai_edits.find_one({
        "str_slide_id": str_slide_id,
        "str_ai_mode": str_ai_mode,
        "str_variant": str_variant or "",
        "str_user_id": str_user_id,
    })


def serialize_slide_doc(dict_doc: dict) -> dict:
    """MongoDB 문서 → JSON-friendly dict (ObjectId/datetime 제거)."""
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
