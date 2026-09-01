"""JWT text text/text text text text

text text:
- Access Token: 15text text
- Refresh Token: 7text text, DB text, text text
- text text: 5text text → 30text text
"""

import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from app.config import settings
from app.models import UserRole
from app.repositories.auth_store import get_user_store, is_auth_store_connected

# ── text ──
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
_VALID_USER_ROLES = {role.value for role in UserRole}

# ── text text text text (text text text text text DB text text) ──
_USER_CACHE: dict[str, tuple[dict, float]] = {}
_USER_CACHE_TTL = 30.0  # 30text — text/text text text text text


def _get_cached_user(str_user_id: str) -> dict | None:
    entry = _USER_CACHE.get(str_user_id)
    if entry and (time.monotonic() - entry[1]) < _USER_CACHE_TTL:
        return entry[0]
    return None


def _set_cached_user(str_user_id: str, dict_user: dict):
    float_now = time.monotonic()
    if len(_USER_CACHE) > 1024:
        float_cutoff = float_now - _USER_CACHE_TTL * 2
        for str_key, (_dict_user, float_ts) in list(_USER_CACHE.items()):
            if float_ts < float_cutoff:
                _USER_CACHE.pop(str_key, None)
    _USER_CACHE[str_user_id] = (dict_user, float_now)


def _normalize_user_role(dict_user: dict) -> dict:
    str_role = str(dict_user.get("str_role") or "").lower()
    if str_role not in _VALID_USER_ROLES:
        dict_user = {**dict_user, "str_role": UserRole.VIEWER.value}
    else:
        dict_user["str_role"] = str_role
    return dict_user


def invalidate_user_cache(str_user_id: str = ""):
    """text text text text text text. text text text text."""
    if str_user_id:
        _USER_CACHE.pop(str_user_id, None)
    else:
        _USER_CACHE.clear()


# ── text text ──
def create_access_token(str_user_id: str, str_role: str) -> str:
    """Access Token text (text text)"""
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
    """Refresh Token text (text text) → (token, expires_at)"""
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
    """text text (text/text text text)"""
    try:
        dict_payload = jwt.decode(
            str_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return dict_payload
    except JWTError:
        return None


# ── Bearer text text ──
def _extract_bearer_token(request: Request) -> str:
    """Authorization text Bearer JWT text.

    text `?token=` query parameter fallback text text, text JWT text
    URL text text(text text·text text·text) text text text
    text. img.src text text text text text HMAC text
    (app.url_signer) text text, JWT text text Authorization text text.
    """
    str_auth_header = request.headers.get("Authorization", "")
    if str_auth_header.startswith("Bearer "):
        return str_auth_header[7:]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Authorization header",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── FastAPI text: text text ──
async def get_current_user(request: Request) -> dict:
    """Access Tokentext text text text text text

    PostgreSQL text text text text text text text (text/text text text)
    """
    if not is_auth_store_connected():
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

    # text text — text text text text text DB text text
    dict_cached = _get_cached_user(str_user_id)
    if dict_cached is not None:
        return dict_cached

    dict_user = await get_user_store().find_by_id(str_user_id, bool_include_secrets=False)

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

    # _idtext text text
    dict_user["_id"] = str(dict_user["_id"])
    dict_user = _normalize_user_role(dict_user)
    _set_cached_user(str_user_id, dict_user)
    return dict_user


# ── text text text text (text/text/text) ──
async def get_media_user(request: Request) -> dict:
    """text(<img src>) text text.

    - Bearer JWT text text get_current_user text text text.
    - text query parameter `?mt=<token>` text text HMAC text (url_signer)
      text text.

    text API text text text text text — text text text
    API text(text text/text/AI text text) text text text text.
    """
    # 1) Bearer text text
    str_auth_header = request.headers.get("Authorization", "")
    if str_auth_header.startswith("Bearer "):
        return await get_current_user(request)

    # 2) text text fallback
    from app.url_signer import verify_media_ticket

    str_ticket = request.query_params.get("mt", "")
    str_user_id = verify_media_ticket(str_ticket)
    if not str_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired media ticket",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # DB text text text text
    if not is_auth_store_connected():
        return {"_id": "anonymous", "str_name": "Anonymous", "str_role": "admin"}

    # text text — text text text text DB text text
    dict_cached = _get_cached_user(str_user_id)
    if dict_cached is not None:
        return dict_cached

    try:
        dict_user = await get_user_store().find_by_id(str_user_id, bool_include_secrets=False)
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
    dict_user = _normalize_user_role(dict_user)
    _set_cached_user(str_user_id, dict_user)
    return dict_user


# ── text text text text (RBAC) text text ──
def require_not_viewer(
    dict_current_user: dict = Depends(get_current_user),
) -> dict:
    """Viewer text text — AI text / annotation text text text text text text.

    Admin, Doctor text text. Viewer text text text text text text/text text.
    """
    str_user_role = dict_current_user.get("str_role", "")
    if str_user_role not in {UserRole.ADMIN.value, UserRole.DOCTOR.value, UserRole.LABELER.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role cannot perform this action",
        )
    return dict_current_user


def require_role(*list_allowed_roles: UserRole):
    """text text text text text text

    text text: Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))
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
