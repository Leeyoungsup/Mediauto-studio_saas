"""감사 로그 (Audit Trail) 미들웨어 및 유틸리티

병원 환경 필수: 모든 접근 기록을 최소 5년 보관
- 누가, 언제, 어디서, 어떤 작업을 했는지 기록
- 불변 로그 (수정/삭제 불가)
- 로그인/슬라이드 열람/AI 분석 등 행위별 action 분류
- HMAC 서명 체인: 각 로그에 이전 로그의 HMAC을 포함해 변조 감지
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

from app.database import get_db

# ── HMAC 체인 서명키 (JWT 시크릿에서 파생) ──
_AUDIT_HMAC_KEY: bytes = b""


def _get_hmac_key() -> bytes:
    global _AUDIT_HMAC_KEY
    if not _AUDIT_HMAC_KEY:
        from app.config import settings
        _AUDIT_HMAC_KEY = hashlib.sha256(
            (settings.JWT_SECRET_KEY + ":audit_log_chain").encode()
        ).digest()
    return _AUDIT_HMAC_KEY


def _compute_log_hmac(dict_log: dict, str_prev_hmac: str = "") -> str:
    """로그 내용 + 이전 HMAC → 현재 HMAC 계산.

    체인 구조: 각 HMAC 에 이전 로그의 HMAC 이 포함되어
    중간 로그 삭제/수정 시 체인이 끊어짐.
    """
    # 서명 대상 필드만 추출 (순서 보장)
    list_fields = [
        str(dict_log.get("str_action", "")),
        str(dict_log.get("str_user_id", "")),
        str(dict_log.get("str_user_email", "")),
        str(dict_log.get("str_resource_type", "")),
        str(dict_log.get("str_resource_id", "")),
        str(dict_log.get("str_detail", "")),
        str(dict_log.get("str_ip_address", "")),
        str(dict_log.get("dt_created_at", "")),
        str_prev_hmac,
    ]
    str_payload = "|".join(list_fields)
    return hmac.new(
        _get_hmac_key(), str_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


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
    dict_before: Optional[dict] = None,
    dict_after: Optional[dict] = None,
) -> Optional[str]:
    """감사 이벤트를 audit_logs 컬렉션에 기록.

    HMAC 체인: 이전 로그의 HMAC 을 참조하여 변조 감지 가능.
    dict_before / dict_after: 변경 전/후 값 (21 CFR Part 11 요건).

    Returns:
        삽입된 로그의 _id 문자열 (후처리 업데이트용). DB 미연결 시 None.
    """
    db = get_db()

    # 이전 로그의 HMAC 조회 (체인 연결)
    str_prev_hmac = ""
    try:
        dict_last = await db.audit_logs.find_one(
            sort=[("dt_created_at", -1)],
            projection={"str_hmac": 1},
        )
        if dict_last:
            str_prev_hmac = dict_last.get("str_hmac", "")
    except Exception:
        pass

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
        "str_prev_hmac": str_prev_hmac,
    }

    # 변경 전/후 값
    if dict_before is not None:
        dict_log["dict_before"] = dict_before
    if dict_after is not None:
        dict_log["dict_after"] = dict_after

    if dict_extra:
        for str_k, v in dict_extra.items():
            if str_k not in dict_log:
                dict_log[str_k] = v

    # HMAC 서명
    dict_log["str_hmac"] = _compute_log_hmac(dict_log, str_prev_hmac)

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
