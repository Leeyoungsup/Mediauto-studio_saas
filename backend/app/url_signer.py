"""미디어 URL 서명 — JWT 를 URL 쿼리에 노출하지 않기 위한 단기 HMAC 티켓

문제:
- <img src> 는 Authorization 헤더를 쓸 수 없어 과거엔 `?token=<JWT>` fallback 을
  허용했다. JWT 가 브라우저 히스토리·프록시 로그·리퍼러에 그대로 남아
  계정 탈취로 이어질 수 있다.

해결:
- 사용자 바인딩 단기(10분) HMAC-SHA256 티켓을 별도로 발급한다.
- 스코프: 미디어 엔드포인트(타일/썸네일/프리뷰) 전용 — API 호출은
  여전히 Bearer 헤더의 JWT 만 받아준다.
- 스테이트리스: DB 조회 불필요, 서명 검증만으로 통과.
- 누출 시 블래스트 반경: 10분 × 미디어 엔드포인트만.

토큰 포맷: `<base64url(user_id|exp)>.<base64url(hmac)>`
"""

import base64
import hashlib
import hmac
import time
from typing import Optional

from app.config import settings

INT_MEDIA_TICKET_TTL_SECONDS = 600  # 10분
STR_KEY_CONTEXT = "media-ticket-v1"


def _get_signing_key() -> bytes:
    """미디어 티켓 전용 서명 키.

    별도 시크릿(MEDIA_SIGNING_KEY) 이 설정되어 있으면 그것을 쓰고,
    없으면 JWT_SECRET_KEY 에서 파생한다. 파생 키는 도메인 분리를 위해
    컨텍스트 문자열을 접두로 추가한 후 SHA-256 으로 해시한다.
    """
    str_key = getattr(settings, "MEDIA_SIGNING_KEY", None) or settings.JWT_SECRET_KEY
    return hashlib.sha256(f"{STR_KEY_CONTEXT}|".encode() + str_key.encode()).digest()


def _b64url_encode(bytes_data: bytes) -> str:
    return base64.urlsafe_b64encode(bytes_data).rstrip(b"=").decode("ascii")


def _b64url_decode(str_data: str) -> bytes:
    int_padding = (-len(str_data)) % 4
    return base64.urlsafe_b64decode(str_data + "=" * int_padding)


def _compute_sig(str_payload: str) -> str:
    bytes_key = _get_signing_key()
    bytes_mac = hmac.new(bytes_key, str_payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(bytes_mac)


def sign_media_ticket(
    str_user_id: str,
    int_ttl_seconds: int = INT_MEDIA_TICKET_TTL_SECONDS,
) -> dict:
    """사용자 바인딩 미디어 티켓 발급.

    Returns:
        {"str_token": "<payload>.<sig>", "int_exp": <unix_ts>, "int_ttl": <seconds>}
    """
    int_exp = int(time.time()) + int_ttl_seconds
    str_payload = f"{str_user_id}|{int_exp}"
    str_payload_b64 = _b64url_encode(str_payload.encode("utf-8"))
    str_sig = _compute_sig(str_payload)
    str_token = f"{str_payload_b64}.{str_sig}"
    return {
        "str_token": str_token,
        "int_exp": int_exp,
        "int_ttl": int_ttl_seconds,
    }


def verify_media_ticket(str_token: str) -> Optional[str]:
    """티켓 검증 — 유효하면 user_id 반환, 무효면 None."""
    if not str_token or "." not in str_token:
        return None
    try:
        str_payload_b64, str_sig = str_token.split(".", 1)
        str_payload = _b64url_decode(str_payload_b64).decode("utf-8")
        str_user_id, str_exp = str_payload.rsplit("|", 1)
        int_exp = int(str_exp)
    except (ValueError, UnicodeDecodeError):
        return None

    if int_exp < int(time.time()):
        return None

    str_expected_sig = _compute_sig(str_payload)
    if not hmac.compare_digest(str_expected_sig, str_sig):
        return None

    return str_user_id
