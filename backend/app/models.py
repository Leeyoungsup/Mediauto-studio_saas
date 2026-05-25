"""text text text text text text

Claude.md text text:
- text text: str_, int_, bool_, dict_, list_, dt_ text
- text: PascalCase
- text: SCREAMING_SNAKE_CASE
- text text text text (None text)
"""

from datetime import datetime, timezone
from enum import Enum

import bcrypt

from app.config import settings

# ── text ──
BCRYPT_COST = 12
# Pepper text text text text text text. text AUTH_PEPPER text
# backend/.secrets.json text 'pepper' text text (app.config text).
_STR_PEPPER = settings.AUTH_PEPPER


class UserRole(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    VIEWER = "viewer"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ── text text ──
def hash_password(str_plain_password: str) -> str:
    """bcrypt + pepper text"""
    str_peppered = str_plain_password + _STR_PEPPER
    bytes_hashed = bcrypt.hashpw(
        str_peppered.encode("utf-8"),
        bcrypt.gensalt(rounds=BCRYPT_COST),
    )
    return bytes_hashed.decode("utf-8")


def verify_password(str_plain_password: str, str_hashed_password: str) -> bool:
    """bcrypt + pepper text"""
    str_peppered = str_plain_password + _STR_PEPPER
    return bcrypt.checkpw(
        str_peppered.encode("utf-8"),
        str_hashed_password.encode("utf-8"),
    )


# ── text text text ──
def create_user_document(
    str_login_id: str,
    str_hashed_password: str,
    str_name: str,
    str_role: str = UserRole.VIEWER,
    str_department: str = "",
    str_approval_status: str = ApprovalStatus.PENDING,
    bool_is_active: bool = False,
    str_approved_by: str = "",
) -> dict:
    """MongoDBtext text text text text

    text `pending` + `is_active=False` — text text text text.
    text admin text admin text text text text text text
    `str_approval_status=ApprovalStatus.APPROVED`, `bool_is_active=True` text text.
    """
    dt_now = datetime.now(timezone.utc)
    return {
        "str_login_id": str_login_id.strip().lower(),
        "str_hashed_password": str_hashed_password,
        "str_name": str_name.strip(),
        "str_role": str_role,
        "str_department": str_department.strip(),
        "str_approval_status": str_approval_status,
        "str_approved_by": str_approved_by,
        "dt_approved_at": dt_now if str_approval_status == ApprovalStatus.APPROVED else None,
        "bool_is_active": bool_is_active,
        "bool_is_locked": False,
        "int_failed_login_attempts": 0,
        "dict_preferences": {
            "annotation_display": {
                "stroke_width": 2,
                "fill_opacity": 0.1,
            },
        },
        "dt_locked_until": None,
        "dt_created_at": dt_now,
        "dt_updated_at": dt_now,
        "dt_last_login": None,
    }
