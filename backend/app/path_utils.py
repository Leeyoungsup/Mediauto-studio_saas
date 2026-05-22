"""Path and filename helpers for upload-backed slide storage."""

from pathlib import Path

from fastapi import HTTPException

from app.config import settings


def rel_path_for(file_path: str) -> str:
    """Return the path relative to uploads/, excluding the filename."""
    try:
        upload_dir = Path(settings.UPLOAD_DIR).resolve()
        path = Path(file_path).resolve()
        rel = path.parent.relative_to(upload_dir)
        value = str(rel).replace("\\", "/")
        return "" if value in (".", "") else value
    except Exception:
        return ""


def safe_subpath(subpath: str) -> Path:
    """Resolve a user-provided folder path and keep it inside uploads/."""
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    target = (upload_dir / subpath).resolve()
    try:
        target.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(400, "Invalid path")
    return target


def safe_filename(filename: str) -> str:
    """Reject path traversal and hidden-file names before joining paths."""
    if not filename:
        raise HTTPException(400, "Filename is required")
    if "/" in filename or "\\" in filename:
        raise HTTPException(400, "Filename cannot contain path separators")
    if filename in (".", ".."):
        raise HTTPException(400, "Invalid filename")
    if "\x00" in filename:
        raise HTTPException(400, "Filename cannot contain NUL characters")
    if filename.startswith("."):
        raise HTTPException(400, "Hidden filenames are not allowed")
    return filename
