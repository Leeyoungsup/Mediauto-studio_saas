"""Runtime operation settings shared by background workers and admin APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.database import get_db, is_db_connected


WORKER_SETTINGS_ID = "worker_control"
DEFAULT_WORKER_SETTINGS = {
    "bool_ai_worker_enabled": True,
    "bool_tile_worker_enabled": True,
}

_dict_worker_settings = DEFAULT_WORKER_SETTINGS.copy()


def get_worker_settings() -> dict[str, bool]:
    return _dict_worker_settings.copy()


async def load_worker_settings() -> dict[str, bool]:
    global _dict_worker_settings
    if not is_db_connected():
        _dict_worker_settings = DEFAULT_WORKER_SETTINGS.copy()
        return get_worker_settings()

    db = get_db()
    dict_doc = await db.app_settings.find_one({"_id": WORKER_SETTINGS_ID}) or {}
    _dict_worker_settings = {
        "bool_ai_worker_enabled": bool(
            dict_doc.get("bool_ai_worker_enabled", DEFAULT_WORKER_SETTINGS["bool_ai_worker_enabled"])
        ),
        "bool_tile_worker_enabled": bool(
            dict_doc.get("bool_tile_worker_enabled", DEFAULT_WORKER_SETTINGS["bool_tile_worker_enabled"])
        ),
    }
    return get_worker_settings()


async def save_worker_settings(
    *,
    bool_ai_worker_enabled: bool,
    bool_tile_worker_enabled: bool,
    str_updated_by: str = "",
) -> dict[str, bool]:
    global _dict_worker_settings
    _dict_worker_settings = {
        "bool_ai_worker_enabled": bool(bool_ai_worker_enabled),
        "bool_tile_worker_enabled": bool(bool_tile_worker_enabled),
    }
    if is_db_connected():
        db = get_db()
        await db.app_settings.update_one(
            {"_id": WORKER_SETTINGS_ID},
            {
                "$set": {
                    **_dict_worker_settings,
                    "str_updated_by": str_updated_by,
                    "dt_updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {
                    "dt_created_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )
    return get_worker_settings()


def serialize_worker_state(dict_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **get_worker_settings(),
        **(dict_extra or {}),
    }
