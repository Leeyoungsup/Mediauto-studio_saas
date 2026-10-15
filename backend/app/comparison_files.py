"""Atomic per-slide, per-account JSON copies of PD-L1 comparison measurements."""
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.config import settings
from app.slide_identity import slide_cache_key


def write_comparison_json(record: dict, slide_path: str) -> Path:
    root = Path(settings.COMPARISON_DIR).resolve()
    relative = Path(slide_path).resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    directory = root / relative.parent / slide_cache_key(slide_path)
    if not directory.resolve().is_relative_to(root):
        raise ValueError("Comparison directory is outside the configured root")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    account = hashlib.sha256(str(record["user_id"]).encode()).hexdigest()[:16]
    target = directory / f"account_{account}.json"
    lock = directory / f".account_{account}.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "a") as locking:
        fcntl.flock(locking.fileno(), fcntl.LOCK_EX)
        measurements = []
        if target.exists() or target.is_symlink():
            with os.fdopen(os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "r") as previous:
                saved = json.load(previous)
            if saved.get("account", {}).get("user_id") != record["user_id"]:
                raise ValueError("Comparison account mismatch")
            measurements = saved["measurements"]
        fields = ("tissue_type", "score_type", "percentage", "grade", "grade_basis",
                  "specialist_elapsed_ms", "ai_result_elapsed_ms", "ai_timing_basis",
                  "ai_json_elapsed_ms", "ai_class_schema", "ai_percentage", "ai_grade", "dt_created_at")
        measurement = {key: record.get(key) for key in fields}
        measurement["measurement_id"] = record["_id"]
        if not any(item["measurement_id"] == record["_id"] for item in measurements):
            measurements.append(measurement)
        # Datetime objects from the DB and ISO strings from disk sort identically in UTC.
        def timestamp(item):
            value = item["dt_created_at"]
            return value.isoformat() if hasattr(value, "isoformat") else str(value)
        measurements.sort(key=timestamp)
        document = {
            "schema_version": 1,
            "slide": {"slide_id": record["slide_id"], "project_path": record["project_path"],
                      "relative_path": relative.as_posix(), "filename": record["filename"]},
            "account": {"user_id": record["user_id"], "name": record.get("user_name", ""),
                        "username": record.get("username", "")},
            "latest": measurements[-1], "measurements": measurements,
        }
        temporary = None
        try:
            handle, temporary = tempfile.mkstemp(prefix=".comparison-", suffix=".tmp", dir=directory)
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump(document, output, ensure_ascii=False, indent=2,
                          default=lambda value: value.isoformat(), allow_nan=False)
                output.write("\n"); output.flush(); os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    return target
