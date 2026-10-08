"""Require a bounded download reason and durable audit insertion before release."""
from fastapi import HTTPException
from app.audit import get_client_ip, log_audit_event


def validate_reason(reason: str) -> str:
    reason = reason.strip()
    if not 2 <= len(reason) <= 200 or any(ord(c) < 32 for c in reason):
        raise HTTPException(422, "Download reason must contain 2-200 characters without control characters")
    return reason


async def record_download(request, user, filename: str, reason: str):
    reason = validate_reason(reason)
    try:
        inserted = await log_audit_event(
            str_action="file.download_requested", str_user_id=user["_id"],
            str_user_email=user.get("str_login_id", ""), str_resource_type="export",
            str_resource_id=filename[:200], str_detail="Download requested",
            str_ip_address=get_client_ip(request), str_user_agent=request.headers.get("User-Agent", ""),
            dict_extra={"download_reason": reason},
        )
        if not inserted:
            raise RuntimeError("Audit insertion did not return an ID")
    except Exception as exc:
        raise HTTPException(503, "Download audit unavailable; export blocked") from exc
