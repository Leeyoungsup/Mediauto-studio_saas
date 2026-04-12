"""사용자 관리 API 라우터 (Admin 전용)

기능:
- 사용자 목록 조회
- 역할 변경
- 계정 활성화/비활성화
- 계정 잠금 해제
- 감사 로그 조회
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.audit import get_client_ip, log_audit_event
from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import UserRole

router = APIRouter()


# ── 사용자 목록 (Admin만) ──
@router.get("/list")
async def list_users(
    int_skip: int = Query(0, ge=0),
    int_limit: int = Query(50, ge=1, le=200),
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """전체 사용자 목록 (페이지네이션)"""
    db = get_db()
    list_users = []
    cursor = db.users.find(
        {},
        {"str_hashed_password": 0},
    ).sort("dt_created_at", -1).skip(int_skip).limit(int_limit)

    async for dict_user in cursor:
        dict_user["_id"] = str(dict_user["_id"])
        list_users.append(dict_user)

    int_total = await db.users.count_documents({})

    return {
        "list_users": list_users,
        "int_total": int_total,
        "int_skip": int_skip,
        "int_limit": int_limit,
    }


# ── 역할 변경 (Admin만) ──
class UpdateRoleRequest(BaseModel):
    str_user_id: str
    str_new_role: str = Field(..., pattern="^(admin|doctor|technician|viewer)$")


@router.post("/role")
async def update_user_role(
    body: UpdateRoleRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """사용자 역할 변경"""
    db = get_db()

    # 자기 자신의 역할은 변경 불가
    if body.str_user_id == dict_current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    result = await db.users.update_one(
        {"_id": ObjectId(body.str_user_id)},
        {
            "$set": {
                "str_role": body.str_new_role,
                "dt_updated_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await log_audit_event(
        str_action="admin.role_changed",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_email", ""),
        str_resource_type="user",
        str_resource_id=body.str_user_id,
        str_detail=f"Role changed to: {body.str_new_role}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": f"Role updated to {body.str_new_role}"}


# ── 계정 활성화/비활성화 (Admin만) ──
class ToggleActiveRequest(BaseModel):
    str_user_id: str
    bool_is_active: bool


@router.post("/toggle-active")
async def toggle_user_active(
    body: ToggleActiveRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """계정 활성/비활성"""
    db = get_db()

    if body.str_user_id == dict_current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    result = await db.users.update_one(
        {"_id": ObjectId(body.str_user_id)},
        {
            "$set": {
                "bool_is_active": body.bool_is_active,
                "dt_updated_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    str_action = "activated" if body.bool_is_active else "deactivated"
    await log_audit_event(
        str_action=f"admin.user_{str_action}",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_email", ""),
        str_resource_type="user",
        str_resource_id=body.str_user_id,
        str_detail=f"Account {str_action}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": f"Account {str_action}"}


# ── 계정 잠금 해제 (Admin만) ──
@router.post("/unlock/{str_user_id}")
async def unlock_user(
    str_user_id: str,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """계정 잠금 해제"""
    db = get_db()

    result = await db.users.update_one(
        {"_id": ObjectId(str_user_id)},
        {
            "$set": {
                "bool_is_locked": False,
                "int_failed_login_attempts": 0,
                "dt_locked_until": None,
                "dt_updated_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await log_audit_event(
        str_action="admin.user_unlocked",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_email", ""),
        str_resource_type="user",
        str_resource_id=str_user_id,
        str_detail="Account unlocked by admin",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": "Account unlocked"}


# ── 감사 로그 조회 (Admin만) ──
@router.get("/audit-logs")
async def get_audit_logs(
    int_skip: int = Query(0, ge=0),
    int_limit: int = Query(100, ge=1, le=500),
    str_action: str = Query(None),
    str_user_id: str = Query(None),
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """감사 로그 조회"""
    db = get_db()
    dict_filter = {}
    if str_action:
        dict_filter["str_action"] = {"$regex": str_action, "$options": "i"}
    if str_user_id:
        dict_filter["str_user_id"] = str_user_id

    list_logs = []
    cursor = db.audit_logs.find(dict_filter).sort("dt_created_at", -1).skip(int_skip).limit(int_limit)

    async for dict_log in cursor:
        dict_log["_id"] = str(dict_log["_id"])
        list_logs.append(dict_log)

    int_total = await db.audit_logs.count_documents(dict_filter)

    return {
        "list_logs": list_logs,
        "int_total": int_total,
        "int_skip": int_skip,
        "int_limit": int_limit,
    }
