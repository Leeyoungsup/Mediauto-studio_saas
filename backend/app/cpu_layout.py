"""CPU worker layout for viewer, AI, tiling, upload, and cell patch jobs.

The app runs several CPU-heavy workloads in one backend process.  Thread
affinity is not perfect isolation, but it prevents long-running background
jobs from freely competing with tile serving and the FastAPI event loop.

Environment overrides:
    MEDIAUTO_CPU_RESERVE
    MEDIAUTO_CPU_WEB
    MEDIAUTO_CPU_VIEWER
    MEDIAUTO_CPU_TILE
    MEDIAUTO_CPU_AI
    MEDIAUTO_CPU_PATCH
    MEDIAUTO_CPU_UPLOAD
"""

from __future__ import annotations

import ctypes
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import FrozenSet, Iterable, List


def _has_linux_affinity_api() -> bool:
    return sys.platform.startswith("linux") and hasattr(os, "sched_setaffinity")


def _has_windows_affinity_api() -> bool:
    return sys.platform.startswith("win")


def _initial_cpus() -> List[int]:
    if _has_linux_affinity_api():
        try:
            return sorted(os.sched_getaffinity(0))
        except Exception:
            pass
    int_n = os.cpu_count() or 1
    return list(range(int_n))


list_all_cpus: List[int] = _initial_cpus()
INT_TOTAL: int = len(list_all_cpus)


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except Exception:
        return default


def _default_counts(total: int) -> dict[str, int]:
    if total <= 1:
        return {"web": 1, "viewer": 1, "tile": 1, "ai": 1, "patch": 1, "upload": 1}

    reserve = _env_int("MEDIAUTO_CPU_RESERVE", max(1, round(total * 0.25)))
    usable = max(1, total - reserve)
    counts = {
        "web": 2 if usable >= 10 else 1,
        "ai": max(1, min(max(1, usable // 5), round(usable * 0.18))),
        "tile": max(1, min(max(1, usable // 8), round(usable * 0.10))),
        "patch": max(1, min(max(1, usable // 10), round(usable * 0.10))),
        "upload": 1,
    }
    used = sum(counts.values())
    counts["viewer"] = max(2 if usable >= 8 else 1, usable - used)
    while sum(counts.values()) > usable:
        for key in ("viewer", "tile", "patch", "ai", "web", "upload"):
            min_value = 2 if key == "viewer" and usable >= 8 else 1
            if counts[key] > min_value:
                counts[key] -= 1
                break
        else:
            break
    return counts


def _trim_counts_to_total(counts: dict[str, int], total: int) -> None:
    while sum(counts.values()) > total:
        for key in ("viewer", "tile", "patch", "ai", "web", "upload"):
            min_value = 2 if key == "viewer" and total >= 8 else 1
            if counts[key] > min_value:
                counts[key] -= 1
                break
        else:
            break


_counts = _default_counts(INT_TOTAL)
_counts["web"] = _env_int("MEDIAUTO_CPU_WEB", _counts["web"])
_counts["viewer"] = _env_int("MEDIAUTO_CPU_VIEWER", _counts["viewer"])
_counts["tile"] = _env_int("MEDIAUTO_CPU_TILE", _counts["tile"])
_counts["ai"] = _env_int("MEDIAUTO_CPU_AI", _counts["ai"])
_counts["patch"] = _env_int("MEDIAUTO_CPU_PATCH", _counts["patch"])
_counts["upload"] = _env_int("MEDIAUTO_CPU_UPLOAD", _counts["upload"])
_trim_counts_to_total(_counts, INT_TOTAL)

# Keep native numeric libraries from oversubscribing every core inside one job.
_native_threads = str(max(1, min(4, _counts["ai"])))
for _env_name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_env_name, _native_threads)


def _take(cursor: int, count: int) -> tuple[list[int], int]:
    if not list_all_cpus:
        return [0], cursor
    count = max(1, int(count))
    out = []
    for idx in range(count):
        out.append(list_all_cpus[(cursor + idx) % len(list_all_cpus)])
    return out, cursor + count


_cursor = 0
list_web_cpus, _cursor = _take(_cursor, _counts["web"])
list_viewer_cpus, _cursor = _take(_cursor, _counts["viewer"])
list_tile_cpus, _cursor = _take(_cursor, _counts["tile"])
list_ai_cpus, _cursor = _take(_cursor, _counts["ai"])
list_patch_cpus, _cursor = _take(_cursor, _counts["patch"])
list_upload_cpus, _cursor = _take(_cursor, _counts["upload"])
list_reserved_cpus = list_all_cpus[_cursor:] if _cursor < len(list_all_cpus) else []

frozenset_web_cpus: FrozenSet[int] = frozenset(list_web_cpus)
frozenset_viewer_cpus: FrozenSet[int] = frozenset(list_viewer_cpus)
frozenset_tile_cpus: FrozenSet[int] = frozenset(list_tile_cpus)
frozenset_ai_cpus: FrozenSet[int] = frozenset(list_ai_cpus)
frozenset_patch_cpus: FrozenSet[int] = frozenset(list_patch_cpus)
frozenset_upload_cpus: FrozenSet[int] = frozenset(list_upload_cpus)
frozenset_reserved_cpus: FrozenSet[int] = frozenset(list_reserved_cpus)

INT_WEB = len(frozenset_web_cpus)
INT_VIEWER = len(frozenset_viewer_cpus)
INT_TILE = len(frozenset_tile_cpus)
INT_AI = len(frozenset_ai_cpus)
INT_PATCH = len(frozenset_patch_cpus)
INT_UPLOAD = len(frozenset_upload_cpus)
INT_RESERVED = len(frozenset_reserved_cpus)

# Backwards-compatible aliases.
list_bg_cpus = list_tile_cpus
frozenset_bg_cpus = frozenset_tile_cpus
INT_BG = INT_TILE


def _windows_affinity_mask(cpus: Iterable[int]) -> int:
    mask = 0
    for cpu in cpus:
        if 0 <= int(cpu) < ctypes.sizeof(ctypes.c_size_t) * 8:
            mask |= 1 << int(cpu)
    return mask or 1


def _pin_to(set_cpus: FrozenSet[int]) -> None:
    if not set_cpus:
        return
    if _has_linux_affinity_api():
        try:
            os.sched_setaffinity(0, set_cpus)
        except Exception as exc:
            print(f"[cpu_layout] linux pin failed: {exc}")
        return
    if _has_windows_affinity_api():
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetThreadAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            kernel32.SetThreadAffinityMask.restype = ctypes.c_size_t
            kernel32.SetThreadAffinityMask(
                kernel32.GetCurrentThread(),
                ctypes.c_size_t(_windows_affinity_mask(set_cpus)),
            )
        except Exception as exc:
            print(f"[cpu_layout] windows pin failed: {exc}")


def _make_initializer(set_cpus: FrozenSet[int]):
    def _init():
        _pin_to(set_cpus)
    return _init


def setup_process_affinity() -> None:
    """Pin the main event-loop thread to the web cores."""
    _pin_to(frozenset_web_cpus)
    print(
        f"[cpu_layout] total={INT_TOTAL} "
        f"web={INT_WEB}({sorted(frozenset_web_cpus)}) "
        f"viewer={INT_VIEWER}({sorted(frozenset_viewer_cpus)}) "
        f"tile={INT_TILE}({sorted(frozenset_tile_cpus)}) "
        f"ai={INT_AI}({sorted(frozenset_ai_cpus)}) "
        f"patch={INT_PATCH}({sorted(frozenset_patch_cpus)}) "
        f"upload={INT_UPLOAD}({sorted(frozenset_upload_cpus)}) "
        f"reserved={INT_RESERVED}({sorted(frozenset_reserved_cpus)})"
    )


viewer_executor = ThreadPoolExecutor(
    max_workers=INT_VIEWER,
    thread_name_prefix="viewer",
    initializer=_make_initializer(frozenset_viewer_cpus),
)

# Cache-miss thumbnails and scanner labels perform blocking WSI reads but must
# not run on the FastAPI event-loop thread or occupy the on-demand tile queue.
media_executor = ThreadPoolExecutor(
    max_workers=max(1, min(2, INT_VIEWER)),
    thread_name_prefix="slide_media",
    initializer=_make_initializer(frozenset_viewer_cpus),
)

tile_executor = ThreadPoolExecutor(
    max_workers=INT_TILE,
    thread_name_prefix="tile_worker",
    initializer=_make_initializer(frozenset_tile_cpus),
)

ai_executor = ThreadPoolExecutor(
    max_workers=INT_AI,
    thread_name_prefix="ai_worker",
    initializer=_make_initializer(frozenset_ai_cpus),
)

patch_executor = ThreadPoolExecutor(
    max_workers=INT_PATCH,
    thread_name_prefix="cell_patch",
    initializer=_make_initializer(frozenset_patch_cpus),
)

# Reading/filtering assistance must not queue behind patch exports or viewer tiles.
assistance_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="cell_assistance",
    initializer=_make_initializer(frozenset_patch_cpus),
)

upload_executor = ThreadPoolExecutor(
    max_workers=INT_UPLOAD,
    thread_name_prefix="upload",
    initializer=_make_initializer(frozenset_upload_cpus),
)

# Backwards-compatible name used by older code paths.
bg_executor = tile_executor


def shutdown_executors() -> None:
    for executor in (
        viewer_executor,
        media_executor,
        tile_executor,
        ai_executor,
        patch_executor,
        assistance_executor,
        upload_executor,
    ):
        executor.shutdown(wait=False, cancel_futures=True)
