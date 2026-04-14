"""감사 로그 (Audit Trail) 미들웨어 및 유틸리티

병원 환경 필수: 모든 접근 기록을 최소 5년 보관
- 누가, 언제, 어디서, 어떤 작업을 했는지 기록
- 불변 로그 (수정/삭제 불가)
- 로그인/슬라이드 열람/AI 분석 등 행위별 action 분류
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

from app.database import get_db


# ── 감사 로그 기록 ──
async def log_audit_event(
    str_action: str,
    str_user_id: Optional[str] = None,
    str_user_email: Optional[str] = None,
    str_resource_type: Optional[str] = None,
    str_resource_id: Optional[str] = None,
    str_detail: str = "",
    str_ip_address: str = "",
    str_user_agent: str = "",
    dict_extra: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """감사 이벤트를 audit_logs 컬렉션에 기록.

    Returns:
        삽입된 로그의 _id 문자열 (후처리 업데이트용). DB 미연결 시 None.
    """
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
    if dict_extra:
        # 예약 키와 충돌 방지
        for str_k, v in dict_extra.items():
            if str_k not in dict_log:
                dict_log[str_k] = v
    result = await db.audit_logs.insert_one(dict_log)
    return str(result.inserted_id)


def get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출 (프록시 뒤에서도 동작)"""
    str_forwarded = request.headers.get("X-Forwarded-For", "")
    if str_forwarded:
        return str_forwarded.split(",")[0].strip()
    str_real = request.headers.get("X-Real-IP", "")
    if str_real:
        return str_real.strip()
    if request.client:
        return request.client.host
    return "unknown"
