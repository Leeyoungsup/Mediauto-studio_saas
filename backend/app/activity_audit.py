"""Bounded activity summaries for authenticated annotation and upload operations."""

import inspect
import logging
import time
from functools import wraps

from fastapi import HTTPException

from app.audit import get_client_ip, log_audit_event

logger = logging.getLogger(__name__)

ANNOTATION_ACTIONS = (
    "annotation.save", "annotation_classes.update", "cell_annotation_classes.update",
    "cell_annotation.regions_save", "cell_annotation.cells_save",
    "cell_annotation.status_update", "cell_annotation.patches_clear",
    "cell_annotation.patches_recompute", "ai.annotation_save", "ai.annotation_delete",
)
ANNOTATION_LOG_ACTIONS = [value for action in ANNOTATION_ACTIONS for value in (action, action + ".failed")]


def audit_activity(action: str, *, resource_type: str = "slide", resource_key: str = "slide_id",
                   success: bool = True):
    """Record route outcomes without copying cell coordinates, memos or request bodies.

    Dependency/validation rejections happen before the route and are not recorded here.
    Logging is best effort, matching existing management actions; errors remain visible
    in the server log and never turn a completed save into an apparent failed save.
    """
    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs).arguments
            request = arguments["request"]
            user = arguments.get("dict_user") or arguments.get("user") or {}
            started = time.monotonic()

            async def record(result=None, error=None):
                try:
                    result = result if isinstance(result, dict) else {}
                    context = {}
                    context["duration_ms"] = round((time.monotonic() - started) * 1000)
                    for key in ("slide_id", "patch_id", "filename", "path", "upload_id", "chunk_index",
                                "total_chunks", "ai_mode", "tissue_type", "variant"):
                        value = arguments.get(key, result.get(key))
                        if isinstance(value, (str, int)):
                            context[key] = value[:500] if isinstance(value, str) else value
                    after = {key: result[key] for key in (
                        "count", "cell_count", "patch_count", "cell_annotation_count",
                        "patch_status", "status", "revision", "deleted", "total_cells",
                        "required_count", "added_count", "excluded_count"
                    ) if key in result and isinstance(result[key], (str, int, bool))}
                    patch = result.get("patch")
                    if isinstance(patch, dict):
                        after.update({key: patch[key] for key in (
                            "str_annotation_status", "str_review_status", "str_termination_status"
                        ) if isinstance(patch.get(key), str)})
                    before = getattr(request.state, "activity_before", None)
                    if isinstance(arguments.get("if_match"), str):
                        before = {"revision": arguments["if_match"]}
                    payload = arguments.get("payload")
                    if isinstance(payload, dict):
                        context["requested_state"] = {key: payload[key][:80] if isinstance(payload[key], str) else payload[key] for key in (
                            "status", "annotation_status", "review_status", "termination_status", "complete"
                        ) if isinstance(payload.get(key), (str, bool))}
                    if error is not None:
                        context["http_status"] = error.status_code if isinstance(error, HTTPException) else 500
                        context["error_type"] = type(error).__name__
                    target = arguments.get(resource_key, result.get(resource_key, ""))
                    await log_audit_event(
                        str_action=action + (".failed" if error else ""),
                        str_user_id=str(user.get("_id", "")),
                        str_user_email=user.get("str_login_id", ""),
                        str_resource_type=resource_type, str_resource_id=str(target)[:255],
                        str_detail=f"{action}: {'failed' if error else 'succeeded'}",
                        str_ip_address=get_client_ip(request),
                        str_user_agent=request.headers.get("User-Agent", ""),
                        dict_extra={"dict_context": context, "str_outcome": "failed" if error else "succeeded"},
                        dict_before=before, dict_after=after if error is None else None,
                    )
                except Exception:
                    logger.exception("Activity audit write failed (%s)", action)

            try:
                result = await function(*args, **kwargs)
            except Exception as error:
                await record(error=error)
                raise
            if success:
                await record(result=result)
            return result

        return wrapped
    return decorate
