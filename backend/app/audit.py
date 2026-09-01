"""text text (Audit Trail) text text text

text text text: text text text text 5text text
- text, text, text, text text text text
- text text (text/text text)
- text/text text/AI text text text action text
- HMAC text text: text text text text HMACtext text text text
"""

import asyncio
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

from app.repositories.operational_store import get_audit_store

# ── HMAC text text (JWT text text) ──
_AUDIT_HMAC_KEY: bytes = b""

# ── text HMAC text text (text DB text text) ──
_last_hmac: str = ""
_last_hmac_loaded: bool = False
_audit_chain_lock = asyncio.Lock()


def _get_hmac_key() -> bytes:
    global _AUDIT_HMAC_KEY
    if not _AUDIT_HMAC_KEY:
        from app.config import settings
        _AUDIT_HMAC_KEY = hashlib.sha256(
            (settings.JWT_SECRET_KEY + ":audit_log_chain").encode()
        ).digest()
    return _AUDIT_HMAC_KEY


def _compute_log_hmac(dict_log: dict, str_prev_hmac: str = "") -> str:
    """text text + text HMAC → text HMAC text.

    text text: text HMAC text text text HMAC text text
    text text text/text text text text.
    """
    # text text text text (text text)
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


async def _ensure_last_hmac_loaded():
    """text text text text text text DBtext text HMACtext text text text."""
    global _last_hmac, _last_hmac_loaded
    if _last_hmac_loaded:
        return
    try:
        _last_hmac = await get_audit_store().latest_hmac()
    except Exception:
        pass
    _last_hmac_loaded = True


def reset_audit_chain_cache() -> None:
    """Reload the chain tail after a backend switch or bulk migration."""
    global _last_hmac, _last_hmac_loaded
    _last_hmac = ""
    _last_hmac_loaded = False


# ── text text text ──
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
    """text text audit_logs text text.

    HMAC text: text text HMAC text text text text text.
    dict_before / dict_after: text text/text text (21 CFR Part 11 text).

    Returns:
        text text _id text (text text). DB text text None.
    """
    global _last_hmac

    # A single append lock prevents concurrent requests from branching the HMAC
    # chain inside this application process.
    async with _audit_chain_lock:
        await _ensure_last_hmac_loaded()
        str_prev_hmac = _last_hmac

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

        if dict_before is not None:
            dict_log["dict_before"] = dict_before
        if dict_after is not None:
            dict_log["dict_after"] = dict_after

        if dict_extra:
            for str_k, v in dict_extra.items():
                if str_k not in dict_log:
                    dict_log[str_k] = v

        str_new_hmac = _compute_log_hmac(dict_log, str_prev_hmac)
        dict_log["str_hmac"] = str_new_hmac
        str_inserted_id = await get_audit_store().insert(dict_log)
        _last_hmac = str_new_hmac
        return str_inserted_id


def _get_trusted_proxies() -> set:
    """env TRUSTED_PROXIES text text IP/CIDR text — text text text text peer text
    X-Forwarded-For / X-Real-IP text text text. text text(text) text text text.

    text: TRUSTED_PROXIES=127.0.0.1,10.0.0.5
    """
    import os as _os
    raw = _os.environ.get("TRUSTED_PROXIES", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


_SET_TRUSTED_PROXIES_CACHE: set = _get_trusted_proxies()


def get_client_ip(request: Request) -> str:
    """text IP text.

    text text text text text text X-Forwarded-For / X-Real-IP text text,
    **TCP peer (`request.client.host`) text TRUSTED_PROXIES env text text text**
    text. text text text text peer text text — text text text
    text text text text rate_limit text text audit log text text
    IP text text text text.
    """
    str_peer = request.client.host if request.client else "unknown"
    if _SET_TRUSTED_PROXIES_CACHE and str_peer in _SET_TRUSTED_PROXIES_CACHE:
        str_forwarded = request.headers.get("X-Forwarded-For", "")
        if str_forwarded:
            return str_forwarded.split(",")[0].strip()
        str_real = request.headers.get("X-Real-IP", "")
        if str_real:
            return str_real.strip()
    return str_peer
