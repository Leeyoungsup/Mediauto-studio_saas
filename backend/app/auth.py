"""JWT 토큰 생성/검증 및 인증 의존성

보안 요구사항:
- Access Token: 15분 만료
- Refresh Token: 7일 만료, DB 저장, 재사용 탐지
- 계정 잠금: 5회 실패 → 30분 잠금
"""

import secrets
import time
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from app.config import settings
from app.database import get_db, is_db_connected
from app.models import UserRole

# ── 상수 ──
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# ── 사용자 정보 단기 캐시 (타일 등 대량 요청 시 DB 부하 방지) ──
_USER_CACHE: dict[str, tuple[dict, float]] = {}
_USER_CACHE_TTL = 30.0  # 30초 — 비활성화/잠금 반영 지연 허용 범위


def _get_cached_user(str_user_id: str) -> dict | None:
    entry = _USER_CACHE.get(str_user_id)
    if entry and (time.monotonic() - entry[1]) < _USER_CACHE_TTL:
        return entry[0]
    return None


def _set_cached_user(str_user_id: str, dict_user: dict):
    _USER_CACHE[str_user_id] = (dict_user, time.monotonic())


def invalidate_user_cache(str_user_id: str = ""):
    """사용자 정보 변경 시 캐시 무효화. 빈 문자열이면 전체 클리어."""
    if str_user_id:
        _USER_CACHE.pop(str_user_id, None)
    else:
        _USER_CACHE.clear()


# ── 토큰 생성 ──
def create_access_token(str_user_id: str, str_role: str) -> str:
    """Access Token 생성 (짧은 수명)"""
    dt_expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    dict_payload = {
        "sub": str_user_id,
        "role": str_role,
        "type": TOKEN_TYPE_ACCESS,
        "exp": dt_expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(
        dict_payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(str_user_id: str) -> tuple:
    """Refresh Token 생성 (긴 수명) → (token, expires_at)"""
    dt_expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    dict_payload = {
        "sub": str_user_id,
        "type": TOKEN_TYPE_REFRESH,
        "exp": dt_expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_urlsafe(16),
    }
    str_token = jwt.encode(
        dict_payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return str_token, dt_expire


def decode_token(str_token: str) -> dict:
    """토큰 디코딩 (만료/서명 검증 포함)"""
    try:
        dict_payload = jwt.decode(
            str_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return dict_payload
    except JWTError:
        return None


# ── Bearer 토큰 추출 ──
def _extract_bearer_token(request: Request) -> str:
    """Authorization 헤더에서만 Bearer JWT 추출.

    과거엔 `?token=` query parameter fallback 을 허용했으나, 이는 JWT 를
    URL 에 노출시켜(브라우저 히스토리·프록시 로그·리퍼러) 계정 탈취 위험이
    있었다. img.src 로 로드되는 미디어는 별도의 단기 HMAC 티켓
    (app.url_signer) 을 사용하며, JWT 는 오직 Authorization 헤더로만 전달된다.
    """
    str_auth_header = request.headers.get("Authorization", "")
    if str_auth_header.startswith("Bearer "):
        return str_auth_header[7:]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Authorization header",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── FastAPI 의존성: 현재 사용자 ──
async def get_current_user(request: Request) -> dict:
    """Access Token에서 현재 사용자 정보를 추출하는 의존성

    MongoDB 미연결 시 인증을 건너뛰고 익명 사용자 반환 (개발/뷰어 전용 모드)
    """
    if not is_db_connected():
        return {"_id": "anonymous", "str_name": "Anonymous", "str_role": "admin"}

    str_token = _extract_bearer_token(request)
    dict_payload = decode_token(str_token)

    if dict_payload is None or dict_payload.get("type") != TOKEN_TYPE_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    str_user_id = dict_payload.get("sub")
    if not str_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # 캐시 확인 — 타일 등 대량 요청 시 DB 부하 방지
    dict_cached = _get_cached_user(str_user_id)
    if dict_cached is not None:
        return dict_cached

    db = get_db()
    dict_user = await db.users.find_one(
        {"_id": ObjectId(str_user_id)},
        {"str_hashed_password": 0},  # 비밀번호는 절대 반환하지 않음
    )

    if dict_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not dict_user.get("bool_is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if dict_user.get("bool_is_locked", False):
        dt_locked_until = dict_user.get("dt_locked_until")
        if dt_locked_until and dt_locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is locked due to too many failed login attempts",
            )

    # _id를 문자열로 변환
    dict_user["_id"] = str(dict_user["_id"])
    _set_cached_user(str_user_id, dict_user)
    return dict_user


# ── 미디어 엔드포인트 전용 인증 (타일/썸네일/프리뷰) ──
async def get_media_user(request: Request) -> dict:
    """미디어(<img src>) 엔드포인트용 의존성.

    - Bearer JWT 가 있으면 get_current_user 와 동일하게 처리한다.
    - 없으면 query parameter `?mt=<token>` 의 단기 HMAC 티켓 (url_signer)
      으로 인증한다.

    일반 API 에는 이 의존성을 달지 않는다 — 미디어 티켓이 누출되어도
    API 호출(슬라이드 삭제/업로드/AI 시작 등) 은 막히도록 스코프를 분리.
    """
    # 1) Bearer 헤더 우선
    str_auth_header = request.headers.get("Authorization", "")
    if str_auth_header.startswith("Bearer "):
        return await get_current_user(request)

    # 2) 미디어 티켓 fallback
    from app.url_signer import verify_media_ticket

    str_ticket = request.query_params.get("mt", "")
    str_user_id = verify_media_ticket(str_ticket)
    if not str_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired media ticket",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # DB 미연결 시 익명 모드
    if not is_db_connected():
        return {"_id": "anonymous", "str_name": "Anonymous", "str_role": "admin"}

    # 캐시 확인 — 타일 대량 요청 시 DB 부하 방지
    dict_cached = _get_cached_user(str_user_id)
    if dict_cached is not None:
        return dict_cached

    db = get_db()
    try:
        dict_user = await db.users.find_one(
            {"_id": ObjectId(str_user_id)},
            {"str_hashed_password": 0},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid media ticket subject",
        )

    if dict_user is None or not dict_user.get("bool_is_active", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    dict_user["_id"] = str(dict_user["_id"])
    _set_cached_user(str_user_id, dict_user)
    return dict_user


# ── 역할 기반 접근 제어 (RBAC) 의존성 팩토리 ──
def require_not_viewer(
    dict_current_user: dict = Depends(get_current_user),
) -> dict:
    """Viewer 역할은 거부 — AI 분석 / annotation 등 읽기 전용 초과 기능 차단.

    Admin, Doctor 만 통과. Viewer 는 로그인은 되어 있지만 결과 쓰기/트리거 불가.
    """
    str_user_role = dict_current_user.get("str_role", "")
    if str_user_role == UserRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer role cannot perform this action",
        )
    return dict_current_user


def require_role(*list_allowed_roles: UserRole):
    """특정 역할만 접근 가능한 의존성 팩토리

    사용 예: Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))
    """
    async def _role_checker(
        dict_current_user: dict = Depends(get_current_user),
    ) -> dict:
        str_user_role = dict_current_user.get("str_role", "")
        list_role_values = [r.value if isinstance(r, UserRole) else r for r in list_allowed_roles]

        if str_user_role not in list_role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {list_role_values}",
            )
        return dict_current_user

    return _role_checker
