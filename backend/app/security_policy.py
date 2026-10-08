"""Server-enforced password age and login-session policy (KP07/KP18)."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.config import settings

PASSWORD_MAX_DAYS = 90


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def password_change_required(user: dict) -> bool:
    changed = utc(user.get("dt_password_changed_at"))
    return changed is None or datetime.now(timezone.utc) >= changed + timedelta(days=PASSWORD_MAX_DAYS)


def check_session(user: dict, session_id: str) -> None:
    if not session_id or session_id != user.get("str_active_session_id"):
        raise HTTPException(401, "Session revoked; please log in again")
    last_activity = utc(user.get("dt_last_activity_at"))
    if last_activity is None or datetime.now(timezone.utc) >= last_activity + timedelta(minutes=settings.SESSION_INACTIVE_MINUTES):
        raise HTTPException(401, "Session expired due to inactivity")
