"""Stable per-slide cache identity helpers."""

import hashlib
import re
from pathlib import Path

from app.config import settings


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def slide_identity_text(file_path: str) -> str:
    """Return path text that should distinguish slide cache ownership."""
    path = Path(file_path)
    try:
        resolved = path.resolve()
        upload_root = Path(settings.UPLOAD_DIR).resolve()
        return resolved.relative_to(upload_root).as_posix()
    except Exception:
        try:
            return path.resolve().as_posix()
        except Exception:
            return path.as_posix()


def slide_cache_key(file_path: str) -> str:
    """Return a filesystem-safe cache key for a slide path.

    The visible prefix keeps caches recognizable while the suffix separates
    same-name files in different folders and same-stem files with different
    extensions.
    """
    text = slide_identity_text(file_path)
    digest = hashlib.sha1(text.lower().encode("utf-8", errors="ignore")).hexdigest()[:12]
    prefix = _SAFE_CHARS.sub("_", Path(file_path).name).strip("._-") or "slide"
    return f"{prefix}__{digest}"
