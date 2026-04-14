"""감사 로그 (Audit Trail) 미들웨어 및 유틸리티

병원 환경 필수: 모든 접근 기록을 최소 5년 보관
- 누가, 언제, 어디서, 어떤 작업을 했는지 기록
- 불변 로그 (수정/삭제 불가)
"""

from datetime import datetime, timezone

from fastapi import Request

from app.database import get_db


# ── 감사 로그 기록 ──
async def log_audit_event(
    str_action: str,
    str_user_id: str = None,
    str_user_email: str = None,
    str_resource_type: str = None,
    str_resource_id: str = None,
    str_detail: str = "",
    str_ip_address: str = "",
    str_user_agent: str = "",
) -> None:
    """감사 이벤트를 audit_logs 컬렉션에 기록"""
    db = get_db()
    dict_log = {
        "str_action": str_action,
        "str_user_id": str_user_id,
        "str_user_email": str_user_email,
        "str_resource_type": str_resource_type,
        "str_resource_id": str_resource_id,
        "str_detail": str_detail,
        "str_ip_address": str_ip_address,
        "str_user_agent": str_user_agent,
        "dt_created_at": datetime.now(timezone.utc),
    }
    await db.audit_logs.insert_one(dict_log)


def get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출 (프록시 뒤에서도 동작)"""
    str_forwarded = request.headers.get("X-Forwarded-For", "")
    if str_forwarded:
        return str_forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
