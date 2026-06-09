"""Admin operation settings API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.audit import get_client_ip, log_audit_event
from app.auth import require_role
from app.models import UserRole
from app.runtime_settings import get_worker_settings, load_worker_settings, save_worker_settings


router = APIRouter()


class WorkerSettingsRequest(BaseModel):
    bool_ai_worker_enabled: bool
    bool_tile_worker_enabled: bool


async def _apply_worker_settings(dict_settings: dict) -> None:
    from app import auto_ai, tile_worker

    if dict_settings.get("bool_tile_worker_enabled"):
        await tile_worker.start_tile_worker()
    else:
        await tile_worker.stop_tile_worker()

    if dict_settings.get("bool_ai_worker_enabled"):
        await auto_ai.start_auto_worker()
    else:
        await auto_ai.stop_auto_worker()


def _worker_status_payload(dict_settings: dict) -> dict:
    from app import auto_ai, tile_worker

    return {
        **dict_settings,
        "bool_ai_worker_running": auto_ai.is_auto_worker_running(),
        "bool_tile_worker_running": tile_worker.is_tile_worker_running(),
    }


@router.get("/settings")
async def get_admin_settings(
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    dict_settings = await load_worker_settings()
    return _worker_status_payload(dict_settings)


@router.put("/settings/workers")
async def update_worker_settings(
    body: WorkerSettingsRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    dict_before = get_worker_settings()
    dict_after = await save_worker_settings(
        bool_ai_worker_enabled=body.bool_ai_worker_enabled,
        bool_tile_worker_enabled=body.bool_tile_worker_enabled,
        str_updated_by=dict_current_user.get("_id", ""),
    )
    await _apply_worker_settings(dict_after)

    await log_audit_event(
        str_action="admin.worker_settings_update",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="settings",
        str_resource_id="worker_control",
        str_detail=(
            f"AI worker {'enabled' if dict_after['bool_ai_worker_enabled'] else 'disabled'}, "
            f"tile worker {'enabled' if dict_after['bool_tile_worker_enabled'] else 'disabled'}"
        ),
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before=dict_before,
        dict_after=dict_after,
    )

    return _worker_status_payload(dict_after)
