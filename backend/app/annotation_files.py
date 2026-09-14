"""Atomic annotation snapshots with optimistic concurrency control."""

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from fastapi import HTTPException

# The application runs one worker. Keep compare-and-replace indivisible between
# its I/O threads; os.replace also keeps readers from observing partial JSON.
_write_lock = threading.Lock()


def read_snapshot(path: Path) -> tuple[bytes, str]:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        data = b"[]"
    return data, '"' + hashlib.sha256(data).hexdigest() + '"'


def save_snapshot(path: Path, payload, expected_revision: str) -> str:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    with _write_lock:
        _, current_revision = read_snapshot(path)
        if expected_revision != current_revision:
            raise HTTPException(409, "Annotations changed in another window. Export your edits before reloading and merging the latest annotations.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
    return '"' + hashlib.sha256(data).hexdigest() + '"'
