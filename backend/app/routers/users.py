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

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.audit import get_client_ip, log_audit_event
from app.auth import get_current_user, invalidate_user_cache, require_role
from app.database import get_db
from app.models import ApprovalStatus, UserRole, create_user_document, hash_password

LOGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]{4,30}$")
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{8,}$"
)

router = APIRouter()


# text text/text text text text text.
# text `str_hashed_password` text text text text text, text text
# `str_totp_secret_enc` (TOTP text, text text text text text text),
# `int_failed_login_attempts` text text text admin UI text text.
# text text text text.
_DICT_USER_PROJECTION_ADMIN = {
    "str_login_id": 1,
    "str_name": 1,
    "str_role": 1,
    "str_department": 1,
    "str_approval_status": 1,
    "str_approved_by": 1,
    "dt_approved_at": 1,
    "bool_is_active": 1,
    "bool_is_locked": 1,
    "dt_locked_until": 1,
    "bool_mfa_enabled": 1,
    "dt_created_at": 1,
    "dt_updated_at": 1,
    "dt_last_login": 1,
}


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
    db = get_db()
    dict_filter = {}
    if str_approval_status:
        dict_filter["str_approval_status"] = str_approval_status
    if str_search:
        str_pat = re.escape(str_search.strip())
        dict_filter["$or"] = [
            {"str_login_id": {"$regex": str_pat, "$options": "i"}},
            {"str_name": {"$regex": str_pat, "$options": "i"}},
            {"str_department": {"$regex": str_pat, "$options": "i"}},
        ]

    list_users = []
    cursor = db.users.find(
        dict_filter,
        _DICT_USER_PROJECTION_ADMIN,
    ).sort("dt_created_at", -1).skip(int_skip).limit(int_limit)

    async for dict_user in cursor:
        dict_user["_id"] = str(dict_user["_id"])
        list_users.append(dict_user)

    int_total = await db.users.count_documents(dict_filter)
    int_pending_total = await db.users.count_documents({"str_approval_status": "pending"})

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
    db = get_db()
    list_pending = []
    cursor = db.users.find(
        {"str_approval_status": ApprovalStatus.PENDING},
        _DICT_USER_PROJECTION_ADMIN,
    ).sort("dt_created_at", 1)
    async for dict_user in cursor:
        dict_user["_id"] = str(dict_user["_id"])
        list_pending.append(dict_user)
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
    db = get_db()
    dict_target = await db.users.find_one({"_id": ObjectId(body.str_user_id)})
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
    await db.users.update_one(
        {"_id": ObjectId(body.str_user_id)},
        {
            "$set": {
                "str_approval_status": ApprovalStatus.APPROVED,
                "str_approved_by": dict_current_user["_id"],
                "dt_approved_at": dt_now,
                "str_role": body.str_new_role,
                "bool_is_active": True,
                "dt_updated_at": dt_now,
            }
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
    db = get_db()
    dict_target = await db.users.find_one({"_id": ObjectId(body.str_user_id)})
    if not dict_target:
        raise HTTPException(404, "User not found")

    dict_before = {
        "str_approval_status": dict_target.get("str_approval_status"),
        "bool_is_active": dict_target.get("bool_is_active"),
    }

    dt_now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": ObjectId(body.str_user_id)},
        {
            "$set": {
                "str_approval_status": ApprovalStatus.REJECTED,
                "bool_is_active": False,
                "dt_updated_at": dt_now,
            }
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
        raise HTTPException(400, "text 4~30text text/text/text text.")
    if not PASSWORD_PATTERN.match(body.str_password):
        raise HTTPException(
            400,
            "text text text/text + text + text text 8text text text.",
        )

    db = get_db()
    dict_existing = await db.users.find_one(
        {"str_login_id": body.str_login_id.strip().lower()}
    )
    if dict_existing:
        raise HTTPException(409, "text text text text.")

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
    result = await db.users.insert_one(dict_doc)
    str_new_user_id = str(result.inserted_id)

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
    db = get_db()
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

    await db.users.update_one(
        {"_id": ObjectId(str_user_id)},
        {
            "$set": {
                "str_name": str_name,
                "str_department": str_department,
                "dt_updated_at": datetime.now(timezone.utc),
            }
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
    db = get_db()
    str_user_id = dict_current_user["_id"]
    dict_current = dict_current_user.get("dict_preferences", {}) or {}
    dict_next = {**dict_current, **(body.dict_preferences or {})}

    await db.users.update_one(
        {"_id": ObjectId(str_user_id)},
        {
            "$set": {
                "dict_preferences": dict_next,
                "dt_updated_at": datetime.now(timezone.utc),
            }
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
    db = get_db()
    dict_target = await db.users.find_one({"_id": ObjectId(body.str_user_id)})
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
                "text text text/text + text + text text 8text text text.",
            )
        dict_updates["str_hashed_password"] = hash_password(body.str_password)
        dict_before["str_password"] = "********"
        dict_after["str_password"] = "********(changed)"
        list_changed.append("password")
        # text text text text text text text text
        await db.sessions.update_many(
            {"str_user_id": body.str_user_id, "bool_is_revoked": False},
            {"$set": {"bool_is_revoked": True}},
        )

    if len(dict_updates) <= 1:
        raise HTTPException(400, "text text text.")

    result = await db.users.update_one(
        {"_id": ObjectId(body.str_user_id)},
        {"$set": dict_updates},
    )
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
        raise HTTPException(400, "text text text text text text.")

    db = get_db()
    dict_target = await db.users.find_one({"_id": ObjectId(str_user_id)})
    if not dict_target:
        raise HTTPException(404, "User not found")

    # text admin text text text
    if dict_target.get("str_role") == UserRole.ADMIN:
        int_admin_count = await db.users.count_documents(
            {"str_role": UserRole.ADMIN, "str_approval_status": ApprovalStatus.APPROVED}
        )
        if int_admin_count <= 1:
            raise HTTPException(400, "text text text text text text.")

    dict_before = {
        "str_login_id": dict_target.get("str_login_id"),
        "str_name": dict_target.get("str_name"),
        "str_role": dict_target.get("str_role"),
        "str_approval_status": dict_target.get("str_approval_status"),
        "bool_is_active": dict_target.get("bool_is_active"),
    }

    await db.users.delete_one({"_id": ObjectId(str_user_id)})
    invalidate_user_cache(str_user_id)
    await db.sessions.update_many(
        {"str_user_id": str_user_id, "bool_is_revoked": False},
        {"$set": {"bool_is_revoked": True}},
    )

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
    db = get_db()

    # text text text text text
    if body.str_user_id == dict_current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    dict_target = await db.users.find_one({"_id": ObjectId(body.str_user_id)})
    if not dict_target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    str_old_role = dict_target.get("str_role", "")

    # text admin text demote text text text
    if body.str_new_role != UserRole.ADMIN and str_old_role == UserRole.ADMIN:
        int_admin_count = await db.users.count_documents(
            {"str_role": UserRole.ADMIN, "str_approval_status": ApprovalStatus.APPROVED}
        )
        if int_admin_count <= 1:
            raise HTTPException(400, "text text text text text text.")

    await db.users.update_one(
        {"_id": ObjectId(body.str_user_id)},
        {
            "$set": {
                "str_role": body.str_new_role,
                "dt_updated_at": datetime.now(timezone.utc),
            }
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
    db = get_db()

    if body.str_user_id == dict_current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    dict_target = await db.users.find_one({"_id": ObjectId(body.str_user_id)})
    if not dict_target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    bool_old_active = dict_target.get("bool_is_active")

    await db.users.update_one(
        {"_id": ObjectId(body.str_user_id)},
        {
            "$set": {
                "bool_is_active": body.bool_is_active,
                "dt_updated_at": datetime.now(timezone.utc),
            }
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
    db = get_db()

    dict_target = await db.users.find_one({"_id": ObjectId(str_user_id)})
    if not dict_target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    dict_before = {
        "bool_is_locked": dict_target.get("bool_is_locked"),
        "int_failed_login_attempts": dict_target.get("int_failed_login_attempts"),
    }

    await db.users.update_one(
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
    db = get_db()
    dict_filter = {"str_action": "user.login_success"}
    if str_user_id:
        dict_filter["str_user_id"] = str_user_id

    list_logs = []
    cursor = db.audit_logs.find(dict_filter).sort("dt_created_at", -1).skip(int_skip).limit(int_limit)
    set_user_ids = set()
    async for dict_log in cursor:
        dict_log["_id"] = str(dict_log["_id"])
        if dict_log.get("str_user_id"):
            set_user_ids.add(dict_log["str_user_id"])
        list_logs.append(dict_log)

    # text text text — 1 query text text
    dict_user_map: dict[str, dict] = {}
    if set_user_ids:
        list_object_ids = []
        for str_uid in set_user_ids:
            try:
                list_object_ids.append(ObjectId(str_uid))
            except Exception:
                continue
        if list_object_ids:
            cursor_users = db.users.find(
                {"_id": {"$in": list_object_ids}},
                {"str_login_id": 1, "str_name": 1, "str_role": 1, "str_department": 1},
            )
            async for dict_u in cursor_users:
                dict_user_map[str(dict_u["_id"])] = {
                    "str_login_id": dict_u.get("str_login_id", ""),
                    "str_name": dict_u.get("str_name", ""),
                    "str_role": dict_u.get("str_role", ""),
                    "str_department": dict_u.get("str_department", ""),
                }

    for dict_log in list_logs:
        str_uid = dict_log.get("str_user_id") or ""
        dict_log["dict_user"] = dict_user_map.get(str_uid, {})

    int_total = await db.audit_logs.count_documents(dict_filter)
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
    db = get_db()

    # text text text text (text user_id text text 403 text text 404 text text text)
    try:
        dict_target = await db.users.find_one(
            {"_id": ObjectId(user_id)},
            {"str_login_id": 1, "str_name": 1, "str_role": 1, "str_department": 1},
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    if not dict_target:
        raise HTTPException(status_code=404, detail="User not found")

    dict_base_filter: dict = {"str_user_id": user_id}
    dict_date_filter = {}
    if str_start_date:
        try:
            dict_date_filter["$gte"] = datetime.fromisoformat(str_start_date).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid str_start_date")
    if str_end_date:
        try:
            dt_end = datetime.fromisoformat(str_end_date).replace(tzinfo=timezone.utc)
            dict_date_filter["$lt"] = dt_end + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid str_end_date")
    if dict_date_filter:
        dict_base_filter["dt_created_at"] = dict_date_filter

    def _with_action(value):
        dict_f = dict_base_filter.copy()
        dict_f["str_action"] = value
        return dict_f

    dict_filter: dict = dict_base_filter.copy()
    if str_category == "login":
        dict_filter["str_action"] = {"$in": ["user.login_success", "user.login_failed", "user.logout"]}
    elif str_category == "slide":
        dict_filter["str_action"] = "slide.view"
    elif str_category == "ai":
        dict_filter["str_action"] = "ai.analyze"
    elif str_category == "project":
        dict_filter["str_action"] = {"$regex": r"^project\."}
    elif str_category == "file":
        dict_filter["str_action"] = {"$in": [
            "folder.create", "folder.rename", "folder.delete",
            "folder.ai_config_update", "folder.ai_config_delete",
            "file.delete", "file.move",
            "slide.upload", "slide.status_update",
        ]}

    list_logs = []
    cursor = db.audit_logs.find(dict_filter).sort("dt_created_at", -1).skip(int_skip).limit(int_limit)
    async for dict_log in cursor:
        dict_log["_id"] = str(dict_log["_id"])
        list_logs.append(dict_log)

    int_total = await db.audit_logs.count_documents(dict_filter)

    # text text text — text text
    dict_counts = {
        "login": await db.audit_logs.count_documents(
            _with_action({"$in": [
                "user.login_success", "user.login_failed", "user.logout",
            ]})
        ),
        "slide": await db.audit_logs.count_documents(
            _with_action("slide.view")
        ),
        "ai": await db.audit_logs.count_documents(
            _with_action("ai.analyze")
        ),
        "project": await db.audit_logs.count_documents(
            _with_action({"$regex": r"^project\."})
        ),
        "file": await db.audit_logs.count_documents(
            _with_action({"$in": [
                "folder.create", "folder.rename", "folder.delete",
                "folder.ai_config_update", "folder.ai_config_delete",
                "file.delete", "file.move",
                "slide.upload", "slide.status_update",
            ]})
        ),
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

    db = get_db()
    list_logs = []
    async for dict_doc in db.audit_logs.find().sort("dt_created_at", 1).limit(int_limit):
        list_logs.append(dict_doc)

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
