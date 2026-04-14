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

    await db.slides.update_one(
        {"str_rel_path": str_rel_path, "str_filename": str_filename},
        dict_update,
    )


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
