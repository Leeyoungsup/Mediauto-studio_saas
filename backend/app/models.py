"""사용자 모델 및 비밀번호 해싱 유틸리티

Claude.md 규칙 준수:
- 변수 접두어: str_, int_, bool_, dict_, list_, dt_ 등
- 클래스: PascalCase
- 상수: SCREAMING_SNAKE_CASE
- 가변 기본 인자 금지 (None 사용)
"""

from datetime import datetime, timezone
from enum import Enum

import bcrypt

# ── 상수 ──
BCRYPT_COST = 12
PEPPER = "MeDICus_2024_P3pp3r"  # 운영 시 환경변수로 분리 권장


class UserRole(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    TECHNICIAN = "technician"
    VIEWER = "viewer"


# ── 비밀번호 해싱 ──
def hash_password(str_plain_password: str) -> str:
    """bcrypt + pepper 해싱"""
    str_peppered = str_plain_password + PEPPER
    bytes_hashed = bcrypt.hashpw(
        str_peppered.encode("utf-8"),
        bcrypt.gensalt(rounds=BCRYPT_COST),
    )
    return bytes_hashed.decode("utf-8")


def verify_password(str_plain_password: str, str_hashed_password: str) -> bool:
    """bcrypt + pepper 검증"""
    str_peppered = str_plain_password + PEPPER
    return bcrypt.checkpw(
        str_peppered.encode("utf-8"),
        str_hashed_password.encode("utf-8"),
    )


# ── 사용자 문서 생성 ──
def create_user_document(
    str_email: str,
    str_hashed_password: str,
    str_name: str,
    str_role: str = UserRole.VIEWER,
    str_department: str = "",
) -> dict:
    """MongoDB에 삽입할 사용자 문서 생성"""
    dt_now = datetime.now(timezone.utc)
    return {
        "str_email": str_email.strip().lower(),
        "str_hashed_password": str_hashed_password,
        "str_name": str_name.strip(),
        "str_role": str_role,
        "str_department": str_department.strip(),
        "bool_is_active": True,
        "bool_is_locked": False,
        "int_failed_login_attempts": 0,
        "dt_locked_until": None,
        "dt_created_at": dt_now,
        "dt_updated_at": dt_now,
        "dt_last_login": None,
    }
