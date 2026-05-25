"""text URL text — JWT text URL text text text text text HMAC text

text:
- <img src> text Authorization text text text text text `?token=<JWT>` fallback text
  text. JWT text text text·text text·text text text
  text text text text text.

text:
- text text text(10text) HMAC-SHA256 text text text.
- text: text text(text/text/text) text — API text
  text Bearer text JWT text text.
- text: DB text text, text text text.
- text text text text: 10text × text text.

text text: `<base64url(user_id|exp)>.<base64url(hmac)>`
"""

import base64
import hashlib
import hmac
import time
from typing import Optional

from app.config import settings

INT_MEDIA_TICKET_TTL_SECONDS = 600  # 10text
STR_KEY_CONTEXT = "media-ticket-v1"


def _get_signing_key() -> bytes:
    """text text text text text.

    text text(MEDIA_SIGNING_KEY) text text text text text,
    text JWT_SECRET_KEY text text. text text text text text
    text text text text text SHA-256 text text.
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
    """text text text text text.

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
    """text text — text user_id text, text None."""
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
