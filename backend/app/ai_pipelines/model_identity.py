"""Model provenance, hashed once per file revision rather than per tile."""

import hashlib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=32)
def _digest(path: str, size: int, mtime_ns: int, ctime_ns: int, inode: int) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def model_identity(path: Path) -> dict:
    path = path.resolve()
    stat = path.stat()
    return {"filename": path.name, "sha256": _digest(
        str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)}
