"""Compact existing AI result JSON cache files.

This script scans ``backend/ai_results`` and rewrites result JSON files whose
``cells`` or ``excluded_cells`` entries still use the old verbose object format:

    {"x": 1.2, "y": 3.4, "class_id": 0, "confidence": 0.99, ...}

into the compact array format used by the current app:

    [x, y, class_id, confidence]
    [x, y, class_id, confidence, hidden, exclude_from_score]

Usage:
    python backend/scripts/compact_ai_result_cache.py
    python backend/scripts/compact_ai_result_cache.py --dry-run
    python backend/scripts/compact_ai_result_cache.py --backup
    python backend/scripts/compact_ai_result_cache.py --root backend/ai_results/Quanti\ PD-L1
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any


PATH_BACKEND = Path(__file__).resolve().parent.parent
PATH_REPO = PATH_BACKEND.parent
if str(PATH_BACKEND) not in sys.path:
    sys.path.insert(0, str(PATH_BACKEND))

try:
    from app.config import settings
except Exception:
    settings = None


SKIP_DIR_NAMES = {
    "__pycache__",
}


def _default_ai_results_root() -> Path:
    if settings is not None:
        return Path(settings.AI_RESULTS_DIR)
    return PATH_BACKEND / "ai_results"


def _compact_number(value: Any, digits: int) -> float:
    try:
        return round(float(value), digits)
    except Exception:
        return 0.0


def _compact_class_id(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _compact_cell(cell: Any) -> Any:
    if isinstance(cell, list):
        return cell
    if not isinstance(cell, dict):
        return cell

    compact = [
        _compact_number(cell.get("x", 0.0), 2),
        _compact_number(cell.get("y", 0.0), 2),
        _compact_class_id(cell.get("class_id", 0)),
        _compact_number(cell.get("confidence", 0.0), 4),
    ]

    hidden = bool(cell.get("hidden"))
    exclude_from_score = bool(cell.get("exclude_from_score"))
    if hidden or exclude_from_score:
        compact.extend([hidden, exclude_from_score])
    return compact


def _needs_compaction(cells: Any) -> bool:
    return bool(cells and isinstance(cells, list) and isinstance(cells[0], dict))


def _compact_payload(payload: Any) -> tuple[Any, bool, int]:
    if not isinstance(payload, dict):
        return payload, False, 0

    changed = False
    total_cells = 0
    for key in ("cells", "excluded_cells"):
        cells = payload.get(key)
        if not isinstance(cells, list):
            continue
        total_cells += len(cells)
        if _needs_compaction(cells):
            payload[key] = [_compact_cell(cell) for cell in cells]
            changed = True

    if changed and isinstance(payload.get("cells"), list):
        payload["total_cells"] = len(payload["cells"])

    return payload, changed, total_cells


def _iter_json_files(root: Path):
    for path in root.rglob("*.json"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name.endswith(".tmp") or path.name.endswith(".bak"):
            continue
        yield path


def _format_mb(bytes_count: int) -> str:
    return f"{bytes_count / 1024 / 1024:.2f} MB"


def compact_file(path: Path, *, dry_run: bool, backup: bool) -> dict[str, Any]:
    before_size = path.stat().st_size
    start = time.time()

    with path.open("r", encoding="utf-8") as file_in:
        payload = json.load(file_in)

    payload, changed, total_cells = _compact_payload(payload)
    if not changed:
        return {
            "path": path,
            "changed": False,
            "before": before_size,
            "after": before_size,
            "cells": total_cells,
            "seconds": time.time() - start,
        }

    if dry_run:
        return {
            "path": path,
            "changed": True,
            "before": before_size,
            "after": None,
            "cells": total_cells,
            "seconds": time.time() - start,
        }

    if backup:
        backup_path = path.with_suffix(path.suffix + ".bak")
        if not backup_path.exists():
            shutil.copy2(path, backup_path)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as file_out:
            json.dump(payload, file_out, separators=(",", ":"))
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "path": path,
        "changed": True,
        "before": before_size,
        "after": path.stat().st_size,
        "cells": total_cells,
        "seconds": time.time() - start,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact AI result cache JSON files.")
    parser.add_argument(
        "--root",
        default=str(_default_ai_results_root()),
        help="AI result cache root directory. Defaults to backend/app settings.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan only; do not rewrite files.")
    parser.add_argument("--backup", action="store_true", help="Create .bak files before rewriting.")
    parser.add_argument(
        "--min-mb",
        type=float,
        default=0.0,
        help="Only inspect files at least this large in MB.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[compact_ai_result_cache] root not found: {root}")
        return 2

    min_bytes = int(args.min_mb * 1024 * 1024)
    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"[compact_ai_result_cache] mode   : {mode}")
    print(f"[compact_ai_result_cache] root   : {root}")
    print(f"[compact_ai_result_cache] backup : {bool(args.backup)}")
    if min_bytes:
        print(f"[compact_ai_result_cache] min    : {_format_mb(min_bytes)}")
    print()

    scanned = 0
    changed = 0
    skipped_small = 0
    failed = 0
    before_total = 0
    after_total = 0
    started = time.time()

    for path in _iter_json_files(root):
        size = path.stat().st_size
        if size < min_bytes:
            skipped_small += 1
            continue
        scanned += 1
        before_total += size
        try:
            result = compact_file(path, dry_run=args.dry_run, backup=args.backup)
        except Exception as exc:
            failed += 1
            after_total += size
            print(f"[FAIL] {path} :: {exc}")
            continue

        if result["changed"]:
            changed += 1
            after_size = result["after"] if result["after"] is not None else result["before"]
            after_total += after_size
            print(
                f"[COMPACT] {path} | cells={result['cells']:,} | "
                f"{_format_mb(result['before'])} -> "
                f"{'dry-run' if result['after'] is None else _format_mb(result['after'])} | "
                f"{result['seconds']:.1f}s"
            )
        else:
            after_total += result["after"]
            print(f"[OK] {path} | already compact | {_format_mb(result['before'])}")

    elapsed = time.time() - started
    print()
    print(f"[compact_ai_result_cache] scanned      : {scanned}")
    print(f"[compact_ai_result_cache] compacted    : {changed}")
    print(f"[compact_ai_result_cache] skipped small: {skipped_small}")
    print(f"[compact_ai_result_cache] failed       : {failed}")
    print(f"[compact_ai_result_cache] size         : {_format_mb(before_total)} -> {_format_mb(after_total)}")
    print(f"[compact_ai_result_cache] elapsed      : {elapsed:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
