"""text API text — text, text, text text, text

text:
- bcrypt + pepper text text
- JWT Access/Refresh Token
- text text 5text → text text 30text
- text text text
"""

import asyncio
import re
import secrets
from app.security_policy import check_session, password_change_required, utc
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.audit import get_client_ip, log_audit_event
from app.geo import enrich_audit_with_geo
from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    require_role,
    _check_user_state,
    TOKEN_TYPE_REFRESH,
)
from app.config import settings
from app.encryption import encrypt_field, decrypt_field
from app.models import ApprovalStatus, UserRole, create_user_document, hash_password, verify_password
from app.repositories.auth_store import get_session_store, get_user_store
from app.totp import generate_totp_secret, verify_totp, build_totp_uri

router = APIRouter()

# ── text ──
PASSWORD_MIN_LENGTH = 9
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{9,}$"
)

# Refresh token rotation grace window.
# text text API text text text text /auth/refresh text text text text text,
# text text text text "text revoked text text" text reuse-detection text text
# text text text text text text text text.
# text text text text "text rotated text" text replacement text text text
# text text text text. text text revoked text text text reuse text
# text text text text text text revoke text.
# Refresh rotation grace window.
# text: 30s — text text text text text
# text: 300s — text/text text suspend text text text text /refresh
#        text text text text. text text text reuse text text text
#        text 5text text.
REFRESH_ROTATION_GRACE_SECONDS = 300


# ── text/text text ──
LOGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]{4,30}$")


class RegisterRequest(BaseModel):
    str_login_id: str = Field(..., min_length=4, max_length=30)
    str_password: str = Field(..., min_length=9, max_length=128)
    str_name: str = Field(..., min_length=1, max_length=100)
    str_department: str = Field(default="", max_length=100)


class LoginRequest(BaseModel):
    str_login_id: str = Field(..., min_length=1, max_length=30)
    str_password: str = Field(..., min_length=1, max_length=128)
    str_totp_code: str = Field(default="", max_length=6)


class TokenResponse(BaseModel):
    str_access_token: str
    str_refresh_token: str
    str_token_type: str = "bearer"
    int_expires_in: int
    dict_user: dict
    bool_password_change_required: bool = False


class MfaRequiredResponse(BaseModel):
    """MFA 1text text text TOTP text text. text text text."""
    bool_mfa_required: bool = True
    str_message: str


class RefreshRequest(BaseModel):
    str_refresh_token: str


# ── text ──
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request):
    """text text text (text text: viewer)"""
    # text text text (4~30text, text/text/text)
    if not LOGIN_ID_PATTERN.match(body.str_login_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login ID must be 4-30 characters and may contain only letters, numbers, and underscores.",
        )

    # text text text
    if not PASSWORD_PATTERN.match(body.str_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 9 characters and include letters, numbers, and a special character.",
        )

    obj_user_store = get_user_store()

    # text text text
    dict_existing = await obj_user_store.find_by_login_id(body.str_login_id)
    if dict_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Login ID already exists.",
        )

    # text text text admin + text text, text viewer + pending
    int_user_count = await obj_user_store.count()
    bool_is_first = int_user_count == 0
    str_role = UserRole.ADMIN if bool_is_first else UserRole.VIEWER
    str_status = ApprovalStatus.APPROVED if bool_is_first else ApprovalStatus.PENDING
    bool_is_active = bool_is_first

    str_hashed = hash_password(body.str_password)
    dict_user_doc = create_user_document(
        str_login_id=body.str_login_id,
        str_hashed_password=str_hashed,
        str_name=body.str_name,
        str_role=str_role,
        str_department=body.str_department,
        str_approval_status=str_status,
        bool_is_active=bool_is_active,
        str_approved_by="system" if bool_is_first else "",
    )

    str_user_id = await obj_user_store.insert(dict_user_doc)

    # text text
    await log_audit_event(
        str_action="user.register",
        str_user_id=str_user_id,
        str_user_email=body.str_login_id,
        str_resource_type="user",
        str_resource_id=str_user_id,
        str_detail=f"New user registered with role: {str_role}, status: {str_status}",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    str_message = (
        "Admin account created successfully."
        if bool_is_first
        else "Registration submitted. Please wait for administrator approval."
    )

    return {
        "str_message": str_message,
        "str_user_id": str_user_id,
        "str_role": str_role,
        "str_approval_status": str_status,
        "bool_requires_approval": not bool_is_first,
    }


# ── text ──
# response_model text text — MFA text text text text 1text
# `MfaRequiredResponse` text dict text text text TokenResponse text text
# pydantic validation text 500 text text. dict text text text text text.
@router.post("/login", responses={
    200: {"model": TokenResponse, "description": "text text text"},
    202: {"model": MfaRequiredResponse, "description": "MFA TOTP text text"},
})
async def login(body: LoginRequest, request: Request):
    """text/text text → Access + Refresh Token text (text MFA 1text text)."""
    obj_user_store = get_user_store()
    obj_session_store = get_session_store()
    str_login_id_lower = body.str_login_id.strip().lower()

    dict_user = await obj_user_store.find_by_login_id(str_login_id_lower)
    if not dict_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login ID or password.",
        )

    str_user_id = str(dict_user["_id"])

    # text text text
    if dict_user.get("bool_is_locked", False):
        dt_locked_until = utc(dict_user.get("dt_locked_until"))
        if dt_locked_until and dt_locked_until > datetime.now(timezone.utc):
            int_remaining_minutes = int(
                (dt_locked_until - datetime.now(timezone.utc)).total_seconds() / 60
            )
            await log_audit_event(
                str_action="user.login_locked",
                str_user_id=str_user_id,
                str_user_email=str_login_id_lower,
                str_detail=f"Login attempt while locked ({int_remaining_minutes}min remaining)",
                str_ip_address=get_client_ip(request),
                str_user_agent=request.headers.get("User-Agent", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account locked. Try again in {int_remaining_minutes} minutes.",
            )
        else:
            # text text text → text
            await obj_user_store.update_by_id(
                str(dict_user["_id"]),
                {"bool_is_locked": False, "int_failed_login_attempts": 0},
            )

    # text text
    if not dict_user.get("bool_is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact administrator.",
        )

    # text text
    if not verify_password(body.str_password, dict_user["str_hashed_password"]):
        int_attempts = await obj_user_store.record_failed_login(
            str_user_id, settings.MAX_LOGIN_ATTEMPTS,
            datetime.now(timezone.utc) + timedelta(minutes=settings.ACCOUNT_LOCK_MINUTES),
        )

        await log_audit_event(
            str_action="user.login_failed",
            str_user_id=str_user_id,
            str_user_email=str_login_id_lower,
            str_detail=f"Failed attempt #{int_attempts}"
            + (" → LOCKED" if int_attempts >= settings.MAX_LOGIN_ATTEMPTS else ""),
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login ID or password.",
        )

    # text text text (text text text — text text text)
    str_approval = dict_user.get("str_approval_status", ApprovalStatus.APPROVED)
    if str_approval == ApprovalStatus.PENDING:
        await log_audit_event(
            str_action="user.login_pending",
            str_user_id=str_user_id,
            str_user_email=str_login_id_lower,
            str_detail="Login attempt on pending account",
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account approval is pending. Please wait for administrator approval.",
        )
    if str_approval == ApprovalStatus.REJECTED:
        await log_audit_event(
            str_action="user.login_rejected",
            str_user_id=str_user_id,
            str_user_email=str_login_id_lower,
            str_detail="Login attempt on rejected account",
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account registration was rejected. Contact administrator.",
        )

    # ── MFA text (text text) ──
    str_encrypted_totp = dict_user.get("str_totp_secret_enc", "")
    bool_mfa_enabled = dict_user.get("bool_mfa_enabled", False)
    if bool_mfa_enabled and str_encrypted_totp:
        if not body.str_totp_code:
            # text text TOTP text text → MFA text text
            return {
                "bool_mfa_required": True,
                "str_message": "Two-factor authentication code is required.",
            }
        str_totp_secret = decrypt_field(str_encrypted_totp)
        if not verify_totp(str_totp_secret, body.str_totp_code):
            await log_audit_event(
                str_action="user.mfa_failed",
                str_user_id=str_user_id,
                str_user_email=str_login_id_lower,
                str_detail="Invalid TOTP code",
                str_ip_address=get_client_ip(request),
                str_user_agent=request.headers.get("User-Agent", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid two-factor authentication code.",
            )

    # text text → text text text
    await obj_user_store.update_by_id(
        str(dict_user["_id"]),
        {
            "int_failed_login_attempts": 0,
            "bool_is_locked": False,
            "dt_last_login": datetime.now(timezone.utc),
        },
    )

    # text text
    str_session_id = secrets.token_urlsafe(32)
    await obj_session_store.revoke_for_user(str_user_id)
    await obj_user_store.update_by_id(str_user_id, {
        "str_active_session_id": str_session_id,
        "dt_last_activity_at": datetime.now(timezone.utc),
    })
    str_access_token = create_access_token(str_user_id, dict_user["str_role"], str_session_id)
    str_refresh_token, dt_refresh_expires = create_refresh_token(str_user_id, str_session_id)

    # Refresh tokentext DBtext text (text text)
    await obj_session_store.insert({
        "str_user_id": str_user_id,
        "str_refresh_token": str_refresh_token,
        "str_ip_address": get_client_ip(request),
        "str_user_agent": request.headers.get("User-Agent", ""),
        "dt_created_at": datetime.now(timezone.utc),
        "dt_expires_at": dt_refresh_expires,
        "bool_is_revoked": False,
    })

    str_client_ip = get_client_ip(request)
    str_login_log_id = await log_audit_event(
        str_action="user.login_success",
        str_user_id=str_user_id,
        str_user_email=str_login_id_lower,
        str_detail="Login successful",
        str_ip_address=str_client_ip,
        str_user_agent=request.headers.get("User-Agent", ""),
    )
    # text text text geo text — text text text text text.
    asyncio.create_task(enrich_audit_with_geo(str_login_log_id, str_client_ip))

    return TokenResponse(
        bool_password_change_required=password_change_required(dict_user),
        str_access_token=str_access_token,
        str_refresh_token=str_refresh_token,
        int_expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        dict_user={
            "str_id": str_user_id,
            "str_login_id": dict_user["str_login_id"],
            "str_name": dict_user["str_name"],
            "str_role": dict_user["str_role"],
            "str_department": dict_user.get("str_department", ""),
            "dict_preferences": dict_user.get("dict_preferences", {}),
        },
    )


# ── text text ──
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, request: Request):
    """Refresh Token → text Access + Refresh Token (text CAS text rotation)

    text text text text:
        text text text read → text → write text text text text text
        text text text text text "active" text text text rotate text
        text text text replacement text text. text
        `find_one_and_update` text CAS (filter: `bool_is_revoked: False`) text text
        text text rotation text text text. text text text text
        "text revoked" text text grace window text text text text text
        text.
    """
    dict_payload = decode_token(body.str_refresh_token)
    if dict_payload is None or dict_payload.get("type") != TOKEN_TYPE_REFRESH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    str_user_id = dict_payload.get("sub")
    obj_user_store = get_user_store()
    obj_session_store = get_session_store()

    # text text text text (text text rotation text text text).
    dict_user = await obj_user_store.find_by_id(str_user_id, bool_include_secrets=False)
    if not dict_user or not dict_user.get("bool_is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    _check_user_state(dict_user)
    str_session_id = dict_payload.get("sid", "")
    check_session(dict_user, str_session_id)
    if password_change_required(dict_user):
        raise HTTPException(403, detail="PASSWORD_CHANGE_REQUIRED")

    # text text text text — CAS text replaced_by text text text text.
    str_new_access = create_access_token(str_user_id, dict_user["str_role"], str_session_id)
    str_new_refresh, dt_new_expires = create_refresh_token(str_user_id, str_session_id)
    dt_now = datetime.now(timezone.utc)

    # ── text CAS: active text revoked text text replacement text text ──
    dict_claimed = await obj_session_store.claim_rotation(
        body.str_refresh_token,
        str_new_refresh,
        dt_now,
    )

    if dict_claimed is not None:
        # CAS text — text text rotation text text. text text insert text text text.
        await obj_session_store.insert({
            "str_user_id": str_user_id,
            "str_refresh_token": str_new_refresh,
            "str_ip_address": get_client_ip(request),
            "str_user_agent": request.headers.get("User-Agent", ""),
            "dt_created_at": dt_now,
            "dt_expires_at": dt_new_expires,
            "bool_is_revoked": False,
        })

        return TokenResponse(
            str_access_token=str_new_access,
            str_refresh_token=str_new_refresh,
            int_expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            dict_user={
                "str_id": str_user_id,
                "str_login_id": dict_user["str_login_id"],
                "str_name": dict_user["str_name"],
                "str_role": dict_user["str_role"],
                "str_department": dict_user.get("str_department", ""),
                "dict_preferences": dict_user.get("dict_preferences", {}),
            },
        )

    # ── CAS text text: text text text text revoked ──
    # text revoked text text text text.
    dict_session = await obj_session_store.find_by_token(body.str_refresh_token)

    if dict_session is None:
        # text text DB text text → text text/text text text.
        await obj_session_store.revoke_for_user(str_user_id, bool_only_active=False)
        await log_audit_event(
            str_action="security.token_reuse_detected",
            str_user_id=str_user_id,
            str_detail="Unknown refresh token presented",
            str_ip_address=get_client_ip(request),
            str_user_agent=request.headers.get("User-Agent", ""),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. All sessions revoked.",
        )

    # text text text revoked: (a) text text text text text,
    # (b) text grace window text slow client text, (c) text reuse.
    dt_rotated = dict_session.get("dt_rotated_at")
    str_replaced_by = dict_session.get("str_replaced_by")
    if dt_rotated is not None and dt_rotated.tzinfo is None:
        dt_rotated = dt_rotated.replace(tzinfo=timezone.utc)
    bool_in_grace = (
        dt_rotated is not None
        and str_replaced_by
        and (dt_now - dt_rotated).total_seconds() < REFRESH_ROTATION_GRACE_SECONDS
    )
    if bool_in_grace:
        dict_repl = await obj_session_store.find_by_token(
            str_replaced_by,
            bool_only_active=True,
        )
        if dict_repl is not None:
            # replacement text text → text access_token text text
            # text refresh_token text text text. rotation text text text.
            str_grace_access = create_access_token(str_user_id, dict_user["str_role"], str_session_id)
            return TokenResponse(
                str_access_token=str_grace_access,
                str_refresh_token=str_replaced_by,
                int_expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                dict_user={
                    "str_id": str_user_id,
                    "str_login_id": dict_user["str_login_id"],
                    "str_name": dict_user["str_name"],
                    "str_role": dict_user["str_role"],
                    "str_department": dict_user.get("str_department", ""),
                    "dict_preferences": dict_user.get("dict_preferences", {}),
                },
            )
    # text text text replacement text → text text revoke text text.
    # text(DB text text) text text text text text text
    # (text suspended text text text). text text 401 text text text text text text.
    # text text text text text text text.
    await log_audit_event(
        str_action="security.refresh_stale_rotation",
        str_user_id=str_user_id,
        str_detail="Refresh presented outside rotation grace window — single request rejected",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token rotated — re-authenticate",
    )


# ── text ──
@router.post("/logout")
async def logout(request: Request, dict_current_user: dict = Depends(get_current_user)):
    """text text text (Refresh Token text)"""
    obj_session_store = get_session_store()
    str_user_id = dict_current_user["_id"]

    # text text text text text text
    int_revoked = await obj_session_store.revoke_for_user(str_user_id)

    await log_audit_event(
        str_action="user.logout",
        str_user_id=str_user_id,
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_detail=f"Logged out — {int_revoked} sessions revoked",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": "Logged out successfully"}


# ── text text text (text/text <img src> text) ──
@router.get("/media-ticket")
async def issue_media_ticket(dict_current_user: dict = Depends(get_current_user)):
    """text HMAC text text text.

    text <img src> text Authorization text text text text,
    text/text URL text text text `?mt=` text text text.
    text 10text TTL, text text, text text text.
    """
    from app.url_signer import sign_media_ticket

    return sign_media_ticket(str(dict_current_user["_id"]) + ":" + dict_current_user["str_active_session_id"])


# ── text text text ──
@router.get("/me")
async def get_me(dict_current_user: dict = Depends(get_current_user)):
    """text text text text"""
    return {
        "str_id": dict_current_user["_id"],
        "str_login_id": dict_current_user["str_login_id"],
        "str_name": dict_current_user["str_name"],
        "str_role": dict_current_user["str_role"],
        "str_department": dict_current_user.get("str_department", ""),
        "dict_preferences": dict_current_user.get("dict_preferences", {}),
        "dt_last_login": dict_current_user.get("dt_last_login"),
        "bool_password_change_required": password_change_required(dict_current_user),
    }


# ── text text ──
class ChangePasswordRequest(BaseModel):
    str_current_password: str = Field(..., min_length=1)
    str_new_password: str = Field(..., min_length=9, max_length=128)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    dict_current_user: dict = Depends(get_current_user),
):
    """text text"""
    if not PASSWORD_PATTERN.match(body.str_new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain uppercase, lowercase, number, and special character",
        )

    obj_user_store = get_user_store()
    obj_session_store = get_session_store()
    dict_user_full = await obj_user_store.find_by_id(dict_current_user["_id"])

    if not verify_password(body.str_current_password, dict_user_full["str_hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if verify_password(body.str_new_password, dict_user_full["str_hashed_password"]):
        raise HTTPException(400, "New password must differ from the current password")
    str_new_hashed = hash_password(body.str_new_password)
    await obj_user_store.update_by_id(
        dict_current_user["_id"],
        {
            "str_hashed_password": str_new_hashed,
            "dt_updated_at": datetime.now(timezone.utc),
        },
    )

    # text text text text text text (text)
    await obj_session_store.revoke_for_user(dict_current_user["_id"])

    await log_audit_event(
        str_action="user.password_changed",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_detail="Password changed — all sessions revoked",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": "Password changed successfully. Please login again."}


# ── MFA text ──
@router.post("/mfa/setup")
async def mfa_setup(
    request: Request,
    dict_current_user: dict = Depends(get_current_user),
):
    """TOTP text text → otpauth URI text (QR text).

    text text text — /mfa/verify text text text text text.
    """
    obj_user_store = get_user_store()
    str_user_id = dict_current_user["_id"]

    # text text text
    if dict_current_user.get("bool_mfa_enabled", False):
        raise HTTPException(400, "MFA is already enabled. Disable first.")

    str_secret = generate_totp_secret()
    str_encrypted = encrypt_field(str_secret)

    # text text text (text text — bool_mfa_enabled text text text)
    await obj_user_store.update_by_id(str_user_id, {"str_totp_secret_enc": str_encrypted})

    str_uri = build_totp_uri(str_secret, dict_current_user.get("str_login_id", ""))
    return {
        "str_secret": str_secret,
        "str_uri": str_uri,
    }


class MfaVerifyRequest(BaseModel):
    str_totp_code: str = Field(..., min_length=6, max_length=6)


@router.post("/mfa/verify")
async def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    dict_current_user: dict = Depends(get_current_user),
):
    """text TOTP text text text MFA text."""
    obj_user_store = get_user_store()
    str_user_id = dict_current_user["_id"]

    dict_user_full = await obj_user_store.find_by_id(str_user_id)
    str_encrypted = dict_user_full.get("str_totp_secret_enc", "")
    if not str_encrypted:
        raise HTTPException(400, "Call /mfa/setup first.")

    str_secret = decrypt_field(str_encrypted)
    if not verify_totp(str_secret, body.str_totp_code):
        raise HTTPException(400, "Invalid TOTP code. Please try again.")

    await obj_user_store.update_by_id(str_user_id, {"bool_mfa_enabled": True})

    await log_audit_event(
        str_action="user.mfa_enabled",
        str_user_id=str_user_id,
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_detail="TOTP MFA activated",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": "MFA enabled successfully."}


@router.post("/mfa/disable")
async def mfa_disable(
    request: Request,
    dict_current_user: dict = Depends(get_current_user),
):
    """MFA text (text text text text — text text text text text)."""
    obj_user_store = get_user_store()
    str_user_id = dict_current_user["_id"]

    await obj_user_store.update_by_id(
        str_user_id,
        {"bool_mfa_enabled": False, "str_totp_secret_enc": ""},
    )

    await log_audit_event(
        str_action="user.mfa_disabled",
        str_user_id=str_user_id,
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_detail="TOTP MFA deactivated",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": "MFA disabled."}


@router.get("/mfa/status")
async def mfa_status(dict_current_user: dict = Depends(get_current_user)):
    """text text MFA text text text."""
    return {"bool_mfa_enabled": dict_current_user.get("bool_mfa_enabled", False)}


@router.post("/activity")
async def record_activity(dict_current_user: dict = Depends(get_current_user)):
    """Explicit foreground user activity; polling and token refresh never touch this clock."""
    dt_cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.SESSION_INACTIVE_MINUTES)
    if not await get_user_store().touch_activity(
        dict_current_user["_id"], dict_current_user["str_active_session_id"], dt_cutoff,
    ):
        raise HTTPException(401, "Session expired")
    return {"int_idle_timeout_seconds": settings.SESSION_INACTIVE_MINUTES * 60}


class DownloadIntentRequest(BaseModel):
    str_reason: str = Field(..., min_length=2, max_length=200)
    str_filename: str = Field(..., min_length=1, max_length=200)


@router.post("/download-intent")
async def download_intent(body: DownloadIntentRequest, request: Request,
                          dict_current_user: dict = Depends(get_current_user)):
    from app.download_security import record_download
    await record_download(request, dict_current_user, body.str_filename, body.str_reason)
    return {"str_status": "recorded"}
