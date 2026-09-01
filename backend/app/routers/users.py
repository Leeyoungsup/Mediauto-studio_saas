"""text text API text (Admin text)

text:
- text text text
- text text
- text text/text
- text text text
- text text text
"""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.audit import get_client_ip, log_audit_event
from app.auth import get_current_user, invalidate_user_cache, require_role
from app.models import ApprovalStatus, UserRole, create_user_document, hash_password
from app.repositories.auth_store import get_session_store, get_user_store
from app.repositories.operational_store import get_audit_store

LOGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]{4,30}$")
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{8,}$"
)

router = APIRouter()


# ── text text (Admintext) ──
@router.get("/list")
async def list_users(
    int_skip: int = Query(0, ge=0),
    int_limit: int = Query(50, ge=1, le=200),
    str_approval_status: str = Query(None, pattern="^(pending|approved|rejected)$"),
    str_search: str = Query(None),
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text (text, text/text text)"""
    obj_user_store = get_user_store()
    list_users = await obj_user_store.list(
        str_status=str_approval_status,
        str_search=str_search,
        int_skip=int_skip,
        int_limit=int_limit,
    )
    int_total = await obj_user_store.count(
        str_status=str_approval_status,
        str_search=str_search,
    )
    int_pending_total = await obj_user_store.count(str_status="pending")

    return {
        "list_users": list_users,
        "int_total": int_total,
        "int_pending_total": int_pending_total,
        "int_skip": int_skip,
        "int_limit": int_limit,
    }


# ── text text text (Admintext) ──
@router.get("/pending")
async def list_pending_users(
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text text"""
    list_pending = await get_user_store().list(
        str_status=ApprovalStatus.PENDING,
        bool_ascending=True,
    )
    return {"list_pending": list_pending, "int_total": len(list_pending)}


# ── text / text (Admintext) ──
class ApprovalRequest(BaseModel):
    str_user_id: str
    str_new_role: str = Field(default="viewer", pattern="^(admin|doctor|labeler|viewer)$")


@router.post("/approve")
async def approve_user(
    body: ApprovalRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text text → text + text text"""
    obj_user_store = get_user_store()
    dict_target = await obj_user_store.find_by_id(body.str_user_id)
    if not dict_target:
        raise HTTPException(404, "User not found")
    if dict_target.get("str_approval_status") == ApprovalStatus.APPROVED:
        raise HTTPException(400, "User is already approved")

    dict_before = {
        "str_approval_status": dict_target.get("str_approval_status"),
        "str_role": dict_target.get("str_role"),
        "bool_is_active": dict_target.get("bool_is_active"),
    }

    dt_now = datetime.now(timezone.utc)
    await obj_user_store.update_by_id(
        body.str_user_id,
        {
            "str_approval_status": ApprovalStatus.APPROVED,
            "str_approved_by": dict_current_user["_id"],
            "dt_approved_at": dt_now,
            "str_role": body.str_new_role,
            "bool_is_active": True,
            "dt_updated_at": dt_now,
        },
    )

    invalidate_user_cache(body.str_user_id)

    await log_audit_event(
        str_action="admin.user_approved",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=body.str_user_id,
        str_detail=f"Approved with role: {body.str_new_role}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before=dict_before,
        dict_after={
            "str_approval_status": ApprovalStatus.APPROVED,
            "str_role": body.str_new_role,
            "bool_is_active": True,
        },
    )
    return {"str_message": "User approved", "str_role": body.str_new_role}


class RejectRequest(BaseModel):
    str_user_id: str
    str_reason: str = Field(default="", max_length=200)


@router.post("/reject")
async def reject_user(
    body: RejectRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text"""
    obj_user_store = get_user_store()
    dict_target = await obj_user_store.find_by_id(body.str_user_id)
    if not dict_target:
        raise HTTPException(404, "User not found")

    dict_before = {
        "str_approval_status": dict_target.get("str_approval_status"),
        "bool_is_active": dict_target.get("bool_is_active"),
    }

    dt_now = datetime.now(timezone.utc)
    await obj_user_store.update_by_id(
        body.str_user_id,
        {
            "str_approval_status": ApprovalStatus.REJECTED,
            "bool_is_active": False,
            "dt_updated_at": dt_now,
        },
    )

    invalidate_user_cache(body.str_user_id)

    await log_audit_event(
        str_action="admin.user_rejected",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=body.str_user_id,
        str_detail=f"Rejected. reason: {body.str_reason or '(none)'}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before=dict_before,
        dict_after={
            "str_approval_status": ApprovalStatus.REJECTED,
            "bool_is_active": False,
        },
    )
    return {"str_message": "User rejected"}


# ── text text text (Admintext) ──
class CreateUserRequest(BaseModel):
    str_login_id: str = Field(..., min_length=4, max_length=30)
    str_password: str = Field(..., min_length=8, max_length=128)
    str_name: str = Field(..., min_length=1, max_length=100)
    str_department: str = Field(default="", max_length=100)
    str_role: str = Field(default="viewer", pattern="^(admin|doctor|labeler|viewer)$")


@router.post("/create")
async def create_user(
    body: CreateUserRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text text (text text + text)"""
    if not LOGIN_ID_PATTERN.match(body.str_login_id):
        raise HTTPException(400, "Login ID must be 4-30 characters and may contain only letters, numbers, and underscores.")
    if not PASSWORD_PATTERN.match(body.str_password):
        raise HTTPException(
            400,
            "Password must be at least 8 characters and include letters, numbers, and a special character.",
        )

    obj_user_store = get_user_store()
    dict_existing = await obj_user_store.find_by_login_id(body.str_login_id)
    if dict_existing:
        raise HTTPException(409, "Login ID already exists.")

    dict_doc = create_user_document(
        str_login_id=body.str_login_id,
        str_hashed_password=hash_password(body.str_password),
        str_name=body.str_name,
        str_role=body.str_role,
        str_department=body.str_department,
        str_approval_status=ApprovalStatus.APPROVED,
        bool_is_active=True,
        str_approved_by=dict_current_user["_id"],
    )
    str_new_user_id = await obj_user_store.insert(dict_doc)

    await log_audit_event(
        str_action="admin.user_created",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=str_new_user_id,
        str_detail=f"Created user {body.str_login_id} with role {body.str_role}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )
    return {
        "str_message": "User created",
        "str_user_id": str_new_user_id,
        "str_login_id": body.str_login_id.strip().lower(),
        "str_role": body.str_role,
    }


# ── text text text (Admintext) ──
class UpdateUserRequest(BaseModel):
    str_user_id: str
    str_name: str = Field(None, max_length=100)
    str_department: str = Field(None, max_length=100)
    str_password: str = Field(None, min_length=8, max_length=128)


class UpdateMyProfileRequest(BaseModel):
    str_name: str = Field(..., min_length=1, max_length=100)
    str_department: str = Field(default="", max_length=100)


class UpdateMyPreferencesRequest(BaseModel):
    dict_preferences: dict = Field(default_factory=dict)


@router.post("/me")
async def update_my_profile(
    body: UpdateMyProfileRequest,
    request: Request,
    dict_current_user: dict = Depends(get_current_user),
):
    """text text text text text/text text."""
    obj_user_store = get_user_store()
    str_user_id = dict_current_user["_id"]
    str_name = body.str_name.strip()
    str_department = body.str_department.strip()
    if not str_name:
        raise HTTPException(400, "Name is required")

    dict_before = {
        "str_name": dict_current_user.get("str_name", ""),
        "str_department": dict_current_user.get("str_department", ""),
    }
    dict_after = {
        "str_name": str_name,
        "str_department": str_department,
    }
    if dict_before == dict_after:
        return {
            "str_message": "No changes",
            "dict_user": {
                "str_id": str_user_id,
                "str_login_id": dict_current_user.get("str_login_id", ""),
                "str_name": dict_current_user.get("str_name", ""),
                "str_role": dict_current_user.get("str_role", ""),
                "str_department": dict_current_user.get("str_department", ""),
                "dict_preferences": dict_current_user.get("dict_preferences", {}),
            },
        }

    await obj_user_store.update_by_id(
        str_user_id,
        {
            "str_name": str_name,
            "str_department": str_department,
            "dt_updated_at": datetime.now(timezone.utc),
        },
    )
    invalidate_user_cache(str_user_id)

    await log_audit_event(
        str_action="user.profile_updated",
        str_user_id=str_user_id,
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=str_user_id,
        str_detail="Updated own profile",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before=dict_before,
        dict_after=dict_after,
    )

    return {
        "str_message": "Profile updated",
        "dict_user": {
            "str_id": str_user_id,
            "str_login_id": dict_current_user.get("str_login_id", ""),
            "str_name": str_name,
            "str_role": dict_current_user.get("str_role", ""),
            "str_department": str_department,
            "dict_preferences": dict_current_user.get("dict_preferences", {}),
        },
    }


@router.post("/me/preferences")
async def update_my_preferences(
    body: UpdateMyPreferencesRequest,
    request: Request,
    dict_current_user: dict = Depends(get_current_user),
):
    """text text UI preferencetext text."""
    obj_user_store = get_user_store()
    str_user_id = dict_current_user["_id"]
    dict_current = dict_current_user.get("dict_preferences", {}) or {}
    dict_next = {**dict_current, **(body.dict_preferences or {})}

    await obj_user_store.update_by_id(
        str_user_id,
        {
            "dict_preferences": dict_next,
            "dt_updated_at": datetime.now(timezone.utc),
        },
    )
    invalidate_user_cache(str_user_id)

    await log_audit_event(
        str_action="user.preferences_updated",
        str_user_id=str_user_id,
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=str_user_id,
        str_detail="Updated own preferences",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before={"dict_preferences": dict_current},
        dict_after={"dict_preferences": dict_next},
    )

    return {
        "str_message": "Preferences updated",
        "dict_preferences": dict_next,
    }


@router.post("/update")
async def update_user(
    body: UpdateUserRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text / text text (text text /role text)"""
    obj_user_store = get_user_store()
    obj_session_store = get_session_store()
    dict_target = await obj_user_store.find_by_id(body.str_user_id)
    if not dict_target:
        raise HTTPException(404, "User not found")

    dict_updates = {"dt_updated_at": datetime.now(timezone.utc)}
    list_changed = []
    dict_before = {}
    dict_after = {}

    if body.str_name is not None and body.str_name.strip():
        dict_before["str_name"] = dict_target.get("str_name")
        dict_updates["str_name"] = body.str_name.strip()
        dict_after["str_name"] = body.str_name.strip()
        list_changed.append("name")
    if body.str_department is not None:
        dict_before["str_department"] = dict_target.get("str_department")
        dict_updates["str_department"] = body.str_department.strip()
        dict_after["str_department"] = body.str_department.strip()
        list_changed.append("department")
    if body.str_password:
        if not PASSWORD_PATTERN.match(body.str_password):
            raise HTTPException(
                400,
                "Password must be at least 8 characters and include letters, numbers, and a special character.",
            )
        dict_updates["str_hashed_password"] = hash_password(body.str_password)
        dict_before["str_password"] = "********"
        dict_after["str_password"] = "********(changed)"
        list_changed.append("password")
        # text text text text text text text text
        await obj_session_store.revoke_for_user(body.str_user_id)

    if len(dict_updates) <= 1:
        raise HTTPException(400, "No changes to update.")

    await obj_user_store.update_by_id(body.str_user_id, dict_updates)
    invalidate_user_cache(body.str_user_id)

    await log_audit_event(
        str_action="admin.user_updated",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=body.str_user_id,
        str_detail=f"Updated fields: {', '.join(list_changed)}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before=dict_before,
        dict_after=dict_after,
    )
    return {"str_message": "User updated", "list_changed": list_changed}


# ── text text (Admintext) ──
@router.delete("/delete/{str_user_id}")
async def delete_user(
    str_user_id: str,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text + text text text text"""
    if str_user_id == dict_current_user["_id"]:
        raise HTTPException(400, "You cannot delete your own account.")

    obj_user_store = get_user_store()
    obj_session_store = get_session_store()
    dict_target = await obj_user_store.find_by_id(str_user_id)
    if not dict_target:
        raise HTTPException(404, "User not found")

    # text admin text text text
    if dict_target.get("str_role") == UserRole.ADMIN:
        int_admin_count = await obj_user_store.count(
            str_role=UserRole.ADMIN,
            str_status=ApprovalStatus.APPROVED,
        )
        if int_admin_count <= 1:
            raise HTTPException(400, "Cannot delete the last approved admin account.")

    dict_before = {
        "str_login_id": dict_target.get("str_login_id"),
        "str_name": dict_target.get("str_name"),
        "str_role": dict_target.get("str_role"),
        "str_approval_status": dict_target.get("str_approval_status"),
        "bool_is_active": dict_target.get("bool_is_active"),
    }

    await obj_user_store.delete_by_id(str_user_id)
    invalidate_user_cache(str_user_id)
    await obj_session_store.revoke_for_user(str_user_id)

    await log_audit_event(
        str_action="admin.user_deleted",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=str_user_id,
        str_detail=f"Deleted user {dict_target.get('str_login_id', '?')}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before=dict_before,
        dict_after=None,
    )
    return {"str_message": "User deleted"}


# ── text text (Admintext) ──
class UpdateRoleRequest(BaseModel):
    str_user_id: str
    str_new_role: str = Field(..., pattern="^(admin|doctor|labeler|viewer)$")


@router.post("/role")
async def update_user_role(
    body: UpdateRoleRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text"""
    obj_user_store = get_user_store()

    # text text text text text
    if body.str_user_id == dict_current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    dict_target = await obj_user_store.find_by_id(body.str_user_id)
    if not dict_target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    str_old_role = dict_target.get("str_role", "")

    # text admin text demote text text text
    if body.str_new_role != UserRole.ADMIN and str_old_role == UserRole.ADMIN:
        int_admin_count = await obj_user_store.count(
            str_role=UserRole.ADMIN,
            str_status=ApprovalStatus.APPROVED,
        )
        if int_admin_count <= 1:
            raise HTTPException(400, "Cannot remove the last approved admin account.")

    await obj_user_store.update_by_id(
        body.str_user_id,
        {
            "str_role": body.str_new_role,
            "dt_updated_at": datetime.now(timezone.utc),
        },
    )

    invalidate_user_cache(body.str_user_id)

    await log_audit_event(
        str_action="admin.role_changed",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=body.str_user_id,
        str_detail=f"Role changed from {str_old_role} to {body.str_new_role}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before={"str_role": str_old_role},
        dict_after={"str_role": body.str_new_role},
    )

    return {"str_message": f"Role updated to {body.str_new_role}"}


# ── text text/text (Admintext) ──
class ToggleActiveRequest(BaseModel):
    str_user_id: str
    bool_is_active: bool


@router.post("/toggle-active")
async def toggle_user_active(
    body: ToggleActiveRequest,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text/text"""
    obj_user_store = get_user_store()

    if body.str_user_id == dict_current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    dict_target = await obj_user_store.find_by_id(body.str_user_id)
    if not dict_target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    bool_old_active = dict_target.get("bool_is_active")

    await obj_user_store.update_by_id(
        body.str_user_id,
        {
            "bool_is_active": body.bool_is_active,
            "dt_updated_at": datetime.now(timezone.utc),
        },
    )

    invalidate_user_cache(body.str_user_id)

    str_action = "activated" if body.bool_is_active else "deactivated"
    await log_audit_event(
        str_action=f"admin.user_{str_action}",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=body.str_user_id,
        str_detail=f"Account {str_action}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before={"bool_is_active": bool_old_active},
        dict_after={"bool_is_active": body.bool_is_active},
    )

    return {"str_message": f"Account {str_action}"}


# ── text text text (Admintext) ──
@router.post("/unlock/{str_user_id}")
async def unlock_user(
    str_user_id: str,
    request: Request,
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text"""
    obj_user_store = get_user_store()
    dict_target = await obj_user_store.find_by_id(str_user_id)
    if not dict_target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    dict_before = {
        "bool_is_locked": dict_target.get("bool_is_locked"),
        "int_failed_login_attempts": dict_target.get("int_failed_login_attempts"),
    }

    await obj_user_store.update_by_id(
        str_user_id,
        {
            "bool_is_locked": False,
            "int_failed_login_attempts": 0,
            "dt_locked_until": None,
            "dt_updated_at": datetime.now(timezone.utc),
        },
    )

    invalidate_user_cache(str_user_id)

    await log_audit_event(
        str_action="admin.user_unlocked",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_resource_type="user",
        str_resource_id=str_user_id,
        str_detail="Account unlocked by admin",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
        dict_before=dict_before,
        dict_after={
            "bool_is_locked": False,
            "int_failed_login_attempts": 0,
        },
    )

    return {"str_message": "Account unlocked"}


# ── text text text (Admintext) ──
@router.get("/audit-logs")
async def get_audit_logs(
    int_skip: int = Query(0, ge=0),
    int_limit: int = Query(100, ge=1, le=500),
    str_action: str = Query(None),
    str_user_id: str = Query(None),
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text"""
    obj_audit_store = get_audit_store()
    dict_filters = {"str_action_search": str_action, "str_user_id": str_user_id}
    list_logs = await obj_audit_store.list(
        int_skip=int_skip, int_limit=int_limit, **dict_filters,
    )
    int_total = await obj_audit_store.count(**dict_filters)

    return {
        "list_logs": list_logs,
        "int_total": int_total,
        "int_skip": int_skip,
        "int_limit": int_limit,
    }


# ═══════════════════════════════════════════════════════════════
# text text (Admin) — text text + text text text
# ═══════════════════════════════════════════════════════════════

@router.get("/activity/logins")
async def get_recent_logins(
    int_limit: int = Query(100, ge=1, le=500),
    int_skip: int = Query(0, ge=0),
    str_user_id: str = Query(None, description="text text text"),
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text text — text text text UI text text.

    audit_logs text str_action='user.login_success' text text text text.
    text text text text (text/text) text text text text.
    """
    obj_audit_store = get_audit_store()
    dict_filters = {
        "str_action_exact": "user.login_success",
        "str_user_id": str_user_id,
    }
    list_logs = await obj_audit_store.list(
        int_skip=int_skip, int_limit=int_limit, **dict_filters,
    )
    set_user_ids = set()
    for dict_log in list_logs:
        if dict_log.get("str_user_id"):
            set_user_ids.add(dict_log["str_user_id"])

    # text text text — 1 query text text
    dict_user_map: dict[str, dict] = {}
    if set_user_ids:
        list_users = await get_user_store().list_by_ids(list(set_user_ids))
        for dict_u in list_users:
            dict_user_map[str(dict_u["_id"])] = {
                "str_login_id": dict_u.get("str_login_id", ""),
                "str_name": dict_u.get("str_name", ""),
                "str_role": dict_u.get("str_role", ""),
                "str_department": dict_u.get("str_department", ""),
            }

    for dict_log in list_logs:
        str_uid = dict_log.get("str_user_id") or ""
        dict_log["dict_user"] = dict_user_map.get(str_uid, {})

    int_total = await obj_audit_store.count(**dict_filters)
    return {
        "list_logs": list_logs,
        "int_total": int_total,
        "int_skip": int_skip,
        "int_limit": int_limit,
    }


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    int_limit: int = Query(200, ge=1, le=1000),
    int_skip: int = Query(0, ge=0),
    str_start_date: str = Query("", description="Start date YYYY-MM-DD"),
    str_end_date: str = Query("", description="End date YYYY-MM-DD"),
    str_category: str = Query(
        "all",
        pattern="^(all|login|slide|ai|project|file)$",
        description="text text text",
    ),
    dict_current_user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text text text — text/text text/AI text.

    - all: text text
    - login: user.login_success / user.login_failed / user.logout
    - slide: slide.view
    - ai:    ai.analyze
    """
    obj_audit_store = get_audit_store()

    # text text text text (text user_id text text 403 text text 404 text text text)
    dict_target = await get_user_store().find_by_id(user_id, bool_include_secrets=False)
    if not dict_target:
        raise HTTPException(status_code=404, detail="User not found")

    dict_base_filter: dict = {"str_user_id": user_id}
    if str_start_date:
        try:
            dict_base_filter["dt_start"] = datetime.fromisoformat(str_start_date).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid str_start_date")
    if str_end_date:
        try:
            dt_end = datetime.fromisoformat(str_end_date).replace(tzinfo=timezone.utc)
            dict_base_filter["dt_end"] = dt_end + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid str_end_date")

    list_login_actions = ["user.login_success", "user.login_failed", "user.logout"]
    list_file_actions = [
        "folder.create", "folder.rename", "folder.delete",
        "folder.ai_config_update", "folder.ai_config_delete",
        "file.delete", "file.move", "slide.upload", "slide.status_update",
    ]

    def _category_filter(str_value: str) -> dict:
        dict_result = dict_base_filter.copy()
        if str_value == "login":
            dict_result["list_actions"] = list_login_actions
        elif str_value == "slide":
            dict_result["str_action_exact"] = "slide.view"
        elif str_value == "ai":
            dict_result["str_action_exact"] = "ai.analyze"
        elif str_value == "project":
            dict_result["str_action_prefix"] = "project."
        elif str_value == "file":
            dict_result["list_actions"] = list_file_actions
        return dict_result

    dict_filter = _category_filter(str_category)
    list_logs = await obj_audit_store.list(
        int_skip=int_skip, int_limit=int_limit, **dict_filter,
    )
    int_total = await obj_audit_store.count(**dict_filter)

    # text text text — text text
    dict_counts = {
        "login": await obj_audit_store.count(**_category_filter("login")),
        "slide": await obj_audit_store.count(**_category_filter("slide")),
        "ai": await obj_audit_store.count(**_category_filter("ai")),
        "project": await obj_audit_store.count(**_category_filter("project")),
        "file": await obj_audit_store.count(**_category_filter("file")),
    }

    return {
        "dict_user": {
            "str_id": str(dict_target["_id"]),
            "str_login_id": dict_target.get("str_login_id", ""),
            "str_name": dict_target.get("str_name", ""),
            "str_role": dict_target.get("str_role", ""),
            "str_department": dict_target.get("str_department", ""),
        },
        "list_logs": list_logs,
        "int_total": int_total,
        "int_skip": int_skip,
        "int_limit": int_limit,
        "dict_counts": dict_counts,
    }


@router.get("/audit-logs/verify-chain")
async def verify_audit_chain(
    int_limit: int = Query(1000, ge=100, le=10000),
    dict_admin: dict = Depends(require_role(UserRole.ADMIN)),
):
    """text text HMAC text text text.

    text int_limit text text text HMAC text text text text.
    """
    from app.audit import _compute_log_hmac

    list_logs = await get_audit_store().list(
        int_limit=int_limit, bool_ascending=True,
    )

    int_total = len(list_logs)
    int_valid = 0
    int_broken = 0
    int_missing_hmac = 0
    list_broken_ids = []

    for i, dict_doc in enumerate(list_logs):
        str_stored_hmac = dict_doc.get("str_hmac", "")
        if not str_stored_hmac:
            int_missing_hmac += 1
            continue

        str_prev_hmac = dict_doc.get("str_prev_hmac", "")
        str_expected = _compute_log_hmac(dict_doc, str_prev_hmac)

        if str_stored_hmac == str_expected:
            int_valid += 1
        else:
            int_broken += 1
            list_broken_ids.append(str(dict_doc.get("_id", "")))

    return {
        "int_total_checked": int_total,
        "int_valid": int_valid,
        "int_broken": int_broken,
        "int_missing_hmac": int_missing_hmac,
        "bool_chain_intact": int_broken == 0,
        "list_broken_ids": list_broken_ids[:20],
    }
