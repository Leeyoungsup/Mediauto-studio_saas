"""인증 API 라우터 — 회원가입, 로그인, 토큰 갱신, 로그아웃

보안:
- bcrypt + pepper 비밀번호 해싱
- JWT Access/Refresh Token
- 로그인 실패 5회 → 계정 잠금 30분
- 감사 로그 기록
"""

import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from app.audit import get_client_ip, log_audit_event
from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    require_role,
    TOKEN_TYPE_REFRESH,
)
from app.config import settings
from app.database import get_db
from app.models import ApprovalStatus, UserRole, create_user_document, hash_password, verify_password

router = APIRouter()

# ── 상수 ──
PASSWORD_MIN_LENGTH = 8
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{8,}$"
)

# Refresh token rotation grace window.
# 프론트가 여러 API 를 병렬로 호출해 동시에 /auth/refresh 가 여러 번 들어오는 경우,
# 첫 호출만 성공하고 나머지는 "이미 revoked 된 토큰" 으로 reuse-detection 에 걸려
# 전체 세션이 무효화되는 레이스 컨디션 방지용 유예 시간.
# 이 시간 안에 들어오는 "방금 rotated 된" 토큰은 replacement 세션의 토큰을 그대로
# 돌려주어 정상 동작하게 한다. 이보다 오래된 revoked 토큰으로 오면 실제 reuse 공격으로
# 간주해 기존 로직대로 사용자 세션을 모두 revoke 한다.
# Refresh rotation grace window.
# 구: 30s — 단일 탭 동시 요청만 커버
# 현: 300s — 모바일/백그라운드 탭이 suspend 후 깨어나 이전 토큰으로 /refresh
#        를 재시도하는 케이스까지 커버. 더 늘리면 진짜 reuse 공격 탐지 창이
#        좁아지므로 5분으로 제한.
REFRESH_ROTATION_GRACE_SECONDS = 300


# ── 요청/응답 스키마 ──
LOGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]{4,30}$")


class RegisterRequest(BaseModel):
    str_login_id: str = Field(..., min_length=4, max_length=30)
    str_password: str = Field(..., min_length=8, max_length=128)
    str_name: str = Field(..., min_length=1, max_length=100)
    str_department: str = Field(default="", max_length=100)


class LoginRequest(BaseModel):
    str_login_id: str = Field(..., min_length=1, max_length=30)
    str_password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    str_access_token: str
    str_refresh_token: str
    str_token_type: str = "bearer"
    int_expires_in: int
    dict_user: dict


class RefreshRequest(BaseModel):
    str_refresh_token: str


# ── 회원가입 ──
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request):
    """신규 사용자 등록 (기본 역할: viewer)"""
    # 아이디 형식 검증 (4~30자, 영문/숫자/언더스코어)
    if not LOGIN_ID_PATTERN.match(body.str_login_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="아이디는 4~30자 영문/숫자/언더스코어만 가능합니다.",
        )

    # 비밀번호 강도 검증
    if not PASSWORD_PATTERN.match(body.str_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호는 영문 대/소문자 + 숫자 + 특수문자 포함 8자 이상이어야 합니다.",
        )

    db = get_db()

    # 아이디 중복 검사
    dict_existing = await db.users.find_one(
        {"str_login_id": body.str_login_id.strip().lower()}
    )
    if dict_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 아이디입니다.",
        )

    # 첫 번째 사용자는 admin + 즉시 승인, 이후는 viewer + pending
    int_user_count = await db.users.count_documents({})
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

    result = await db.users.insert_one(dict_user_doc)
    str_user_id = str(result.inserted_id)

    # 감사 로그
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
        "회원가입 성공! 바로 로그인할 수 있습니다."
        if bool_is_first
        else "회원가입이 완료되었습니다. 관리자 승인 후 로그인 가능합니다."
    )

    return {
        "str_message": str_message,
        "str_user_id": str_user_id,
        "str_role": str_role,
        "str_approval_status": str_status,
        "bool_requires_approval": not bool_is_first,
    }


# ── 로그인 ──
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    """아이디/비밀번호 로그인 → Access + Refresh Token 발급"""
    db = get_db()
    str_login_id_lower = body.str_login_id.strip().lower()

    dict_user = await db.users.find_one({"str_login_id": str_login_id_lower})
    if not dict_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    str_user_id = str(dict_user["_id"])

    # 계정 잠금 확인
    if dict_user.get("bool_is_locked", False):
        dt_locked_until = dict_user.get("dt_locked_until")
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
            # 잠금 시간 경과 → 해제
            await db.users.update_one(
                {"_id": dict_user["_id"]},
                {"$set": {"bool_is_locked": False, "int_failed_login_attempts": 0}},
            )

    # 비활성 계정
    if not dict_user.get("bool_is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact administrator.",
        )

    # 비밀번호 검증
    if not verify_password(body.str_password, dict_user["str_hashed_password"]):
        int_attempts = dict_user.get("int_failed_login_attempts", 0) + 1
        dict_update = {"$set": {"int_failed_login_attempts": int_attempts}}

        if int_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            dt_lock_until = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCOUNT_LOCK_MINUTES
            )
            dict_update["$set"]["bool_is_locked"] = True
            dict_update["$set"]["dt_locked_until"] = dt_lock_until

        await db.users.update_one({"_id": dict_user["_id"]}, dict_update)

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
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    # 승인 상태 검증 (비밀번호 확인 후 — 계정 열거 방지)
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
            detail="관리자 승인 대기 중입니다. 승인 완료 후 로그인 가능합니다.",
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
            detail="가입 요청이 거부된 계정입니다. 관리자에게 문의하세요.",
        )

    # 로그인 성공 → 실패 카운터 초기화
    await db.users.update_one(
        {"_id": dict_user["_id"]},
        {
            "$set": {
                "int_failed_login_attempts": 0,
                "bool_is_locked": False,
                "dt_last_login": datetime.now(timezone.utc),
            }
        },
    )

    # 토큰 생성
    str_access_token = create_access_token(str_user_id, dict_user["str_role"])
    str_refresh_token, dt_refresh_expires = create_refresh_token(str_user_id)

    # Refresh token을 DB에 저장 (세션 관리)
    await db.sessions.insert_one({
        "str_user_id": str_user_id,
        "str_refresh_token": str_refresh_token,
        "str_ip_address": get_client_ip(request),
        "str_user_agent": request.headers.get("User-Agent", ""),
        "dt_created_at": datetime.now(timezone.utc),
        "dt_expires_at": dt_refresh_expires,
        "bool_is_revoked": False,
    })

    await log_audit_event(
        str_action="user.login_success",
        str_user_id=str_user_id,
        str_user_email=str_login_id_lower,
        str_detail="Login successful",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return TokenResponse(
        str_access_token=str_access_token,
        str_refresh_token=str_refresh_token,
        int_expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        dict_user={
            "str_id": str_user_id,
            "str_login_id": dict_user["str_login_id"],
            "str_name": dict_user["str_name"],
            "str_role": dict_user["str_role"],
            "str_department": dict_user.get("str_department", ""),
        },
    )


# ── 토큰 갱신 ──
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, request: Request):
    """Refresh Token → 새 Access + Refresh Token (원자적 CAS 기반 rotation)

    동시 호출 레이스 방지:
        과거엔 세션을 먼저 read → 검사 → write 하는 방식이라 두 요청이 동시에
        같은 토큰으로 들어오면 둘 다 "active" 라고 판정하고 각자 rotate 해
        중복 세션이 생기거나 replacement 포인터가 덮어쓰였다. 지금은
        `find_one_and_update` 로 CAS (filter: `bool_is_revoked: False`) 를 걸어
        한 요청만 rotation 을 획득하게 한다. 경합에서 진 요청은 자연스럽게
        "이미 revoked" 분기로 떨어져 grace window 검사를 거쳐 동일한 새 토큰을
        돌려받는다.
    """
    dict_payload = decode_token(body.str_refresh_token)
    if dict_payload is None or dict_payload.get("type") != TOKEN_TYPE_REFRESH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    str_user_id = dict_payload.get("sub")
    db = get_db()

    # 사용자 정보 먼저 조회 (비활성 사용자면 rotation 자체를 하지 않음).
    dict_user = await db.users.find_one(
        {"_id": ObjectId(str_user_id)},
        {"str_hashed_password": 0},
    )
    if not dict_user or not dict_user.get("bool_is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    # 새 토큰 미리 생성 — CAS 에서 replaced_by 로 기록할 필요 때문.
    str_new_access = create_access_token(str_user_id, dict_user["str_role"])
    str_new_refresh, dt_new_expires = create_refresh_token(str_user_id)
    dt_now = datetime.now(timezone.utc)

    # ── 원자적 CAS: active 세션을 revoked 로 뒤집으면서 replacement 포인터 기록 ──
    dict_claimed = await db.sessions.find_one_and_update(
        {
            "str_refresh_token": body.str_refresh_token,
            "bool_is_revoked": False,
        },
        {"$set": {
            "bool_is_revoked": True,
            "dt_rotated_at": dt_now,
            "str_replaced_by": str_new_refresh,
        }},
        return_document=ReturnDocument.AFTER,
    )

    if dict_claimed is not None:
        # CAS 승리 — 이 요청이 rotation 을 획득. 새 세션 insert 후 토큰 반환.
        await db.sessions.insert_one({
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
            },
        )

    # ── CAS 실패 경로: 토큰이 존재하지 않거나 이미 revoked ──
    # 세션을 revoked 여부 무관하게 단건 조회.
    dict_session = await db.sessions.find_one({
        "str_refresh_token": body.str_refresh_token,
    })

    if dict_session is None:
        # 토큰 자체가 DB 에 없음 → 진짜 위조/폐기 후 재사용.
        await db.sessions.update_many(
            {"str_user_id": str_user_id},
            {"$set": {"bool_is_revoked": True}},
        )
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

    # 세션은 존재하지만 이미 revoked: (a) 동시 호출에서 내가 진 경우,
    # (b) 레거시 grace window 내 slow client 호출, (c) 진짜 reuse.
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
        dict_repl = await db.sessions.find_one({
            "str_refresh_token": str_replaced_by,
            "bool_is_revoked": False,
        })
        if dict_repl is not None:
            # replacement 세션이 살아있음 → 새 access_token 만 재발급하고
            # 동일한 refresh_token 을 그대로 돌려준다. rotation 은 연쇄하지 않음.
            str_grace_access = create_access_token(str_user_id, dict_user["str_role"])
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
                },
            )
    # 유예 밖 또는 replacement 사라짐 → 의심스럽지만 전체 revoke 는 과잉.
    # 알려진(DB 에 존재하는) 세션이므로 진짜 위조가 아닐 가능성이 높다
    # (오래 suspended 되었던 탭 등). 이 요청만 401 로 거부하고 다른 세션은 건드리지 않는다.
    # 감사 로그는 남겨 패턴 분석이 가능하도록 한다.
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


# ── 로그아웃 ──
@router.post("/logout")
async def logout(request: Request, dict_current_user: dict = Depends(get_current_user)):
    """현재 세션 로그아웃 (Refresh Token 폐기)"""
    db = get_db()
    str_user_id = dict_current_user["_id"]

    # 해당 사용자의 모든 활성 세션 폐기
    result = await db.sessions.update_many(
        {"str_user_id": str_user_id, "bool_is_revoked": False},
        {"$set": {"bool_is_revoked": True}},
    )

    await log_audit_event(
        str_action="user.logout",
        str_user_id=str_user_id,
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_detail=f"Logged out — {result.modified_count} sessions revoked",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": "Logged out successfully"}


# ── 미디어 티켓 발급 (타일/썸네일 <img src> 용) ──
@router.get("/media-ticket")
async def issue_media_ticket(dict_current_user: dict = Depends(get_current_user)):
    """단기 HMAC 미디어 티켓 발급.

    브라우저의 <img src> 는 Authorization 헤더를 설정할 수 없으므로,
    타일/썸네일 URL 에는 이 티켓을 `?mt=` 쿼리로 붙여 사용한다.
    티켓은 10분 TTL, 사용자 바인딩, 미디어 엔드포인트에만 유효.
    """
    from app.url_signer import sign_media_ticket

    return sign_media_ticket(str(dict_current_user["_id"]))


# ── 현재 사용자 정보 ──
@router.get("/me")
async def get_me(dict_current_user: dict = Depends(get_current_user)):
    """현재 로그인된 사용자 정보"""
    return {
        "str_id": dict_current_user["_id"],
        "str_login_id": dict_current_user["str_login_id"],
        "str_name": dict_current_user["str_name"],
        "str_role": dict_current_user["str_role"],
        "str_department": dict_current_user.get("str_department", ""),
        "dt_last_login": dict_current_user.get("dt_last_login"),
    }


# ── 비밀번호 변경 ──
class ChangePasswordRequest(BaseModel):
    str_current_password: str = Field(..., min_length=1)
    str_new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    dict_current_user: dict = Depends(get_current_user),
):
    """비밀번호 변경"""
    if not PASSWORD_PATTERN.match(body.str_new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain uppercase, lowercase, number, and special character",
        )

    db = get_db()
    dict_user_full = await db.users.find_one({"_id": ObjectId(dict_current_user["_id"])})

    if not verify_password(body.str_current_password, dict_user_full["str_hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    str_new_hashed = hash_password(body.str_new_password)
    await db.users.update_one(
        {"_id": ObjectId(dict_current_user["_id"])},
        {
            "$set": {
                "str_hashed_password": str_new_hashed,
                "dt_updated_at": datetime.now(timezone.utc),
            }
        },
    )

    # 비밀번호 변경 시 모든 세션 무효화 (보안)
    await db.sessions.update_many(
        {"str_user_id": dict_current_user["_id"], "bool_is_revoked": False},
        {"$set": {"bool_is_revoked": True}},
    )

    await log_audit_event(
        str_action="user.password_changed",
        str_user_id=dict_current_user["_id"],
        str_user_email=dict_current_user.get("str_login_id", ""),
        str_detail="Password changed — all sessions revoked",
        str_ip_address=get_client_ip(request),
        str_user_agent=request.headers.get("User-Agent", ""),
    )

    return {"str_message": "Password changed successfully. Please login again."}
