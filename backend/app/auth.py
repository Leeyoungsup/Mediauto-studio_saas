"""JWT 토큰 생성/검증 및 인증 의존성

보안 요구사항:
- Access Token: 15분 만료
- Refresh Token: 7일 만료, DB 저장, 재사용 탐지
- 계정 잠금: 5회 실패 → 30분 잠금
"""

import secrets
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
    """Authorization 헤더 또는 query parameter에서 토큰 추출

    이미지 URL(img.src)은 Authorization 헤더를 설정할 수 없으므로
    ?token= 쿼리 파라미터도 허용한다.
    """
    str_auth_header = request.headers.get("Authorization", "")
    if str_auth_header.startswith("Bearer "):
        return str_auth_header[7:]

    # 이미지/타일 URL용 query parameter fallback
    str_query_token = request.query_params.get("token")
    if str_query_token:
        return str_query_token

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
    return dict_user


# ── 역할 기반 접근 제어 (RBAC) 의존성 팩토리 ──
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
