"""text text text janitor — LRU + text text eviction.

text:
- settings.TILE_CACHE_QUOTA_BYTES text text text text text text text.
- "text" text: `.complete` text text mtime (tiles.py text text text throttled touch).
  text text text mtime fallback.
- text slide_manager text text text (text text) text text — stem text text text skip.
- text text DB `bool_tiles_ready` text False text text tile_worker text text text text.
- text stale text tile dir (text tile_worker startup validation text text) text
  text — text text text text text text text.

Claude.md text text (str_/int_/bool_/list_/dict_/float_ text).
"""

import asyncio
import shutil
from pathlib import Path
from typing import List, Tuple


def _dir_size(path: Path) -> int:
    int_total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    int_total += p.stat().st_size
            except Exception:
                continue
    except Exception:
        return 0
    return int_total


def _entry_atime(tiles_dir: Path) -> float:
    marker = tiles_dir / ".complete"
    try:
        if marker.exists():
            return marker.stat().st_mtime
        return tiles_dir.stat().st_mtime
    except Exception:
        return 0.0


def _active_tile_keys():
    from app import tile_generator
    from app.slide_manager import slide_manager

    keys = set()
    for info in slide_manager.list_slides().values():
        try:
            keys.add(tile_generator.get_tiles_dir_for_path(info["file_path"]).name)
        except Exception:
            continue
    return keys


def _inspect_tiles(full_path, active_keys):
    from app import tile_generator

    directory = tile_generator.get_tiles_dir_for_path(full_path)
    if directory.name in active_keys or not directory.exists():
        return None
    return directory, _dir_size(directory), _entry_atime(directory)


def _remove_tiles(directory):
    # A viewer may have opened the slide while the lengthy size scan ran.
    if directory.name in _active_tile_keys():
        return False
    shutil.rmtree(directory)
    return True


async def run_janitor_once() -> None:
    """text text text LRU text eviction 1text text."""
    from app.config import settings
    from app.database import is_db_connected, get_db
    from app import slide_store

    int_quota = settings.TILE_CACHE_QUOTA_BYTES
    if int_quota <= 0:
        return
    if not is_db_connected():
        return

    db = get_db()

    # Filesystem traversal/stat and removal must never run on the event loop.
    # Use the existing bounded tile pool, with its background CPU affinity.
    from app.cpu_layout import bg_executor
    loop = asyncio.get_running_loop()
    set_active_keys = await loop.run_in_executor(bg_executor, _active_tile_keys)

    list_entries: List[Tuple[float, int, str, str, Path]] = []
    int_total = 0

    cursor = db.slides.find(
        {"bool_tiles_ready": True},
        {"str_filename": 1, "str_full_path": 1, "str_rel_path": 1, "_id": 0},
    )
    async for dict_slide in cursor:
        str_filename = dict_slide.get("str_filename") or ""
        str_full_path = dict_slide.get("str_full_path") or ""
        if not str_filename or not str_full_path:
            continue
        entry = await loop.run_in_executor(
            bg_executor, _inspect_tiles, str_full_path, set_active_keys
        )
        if entry is None:
            continue
        tiles_dir, int_size, float_atime = entry
        list_entries.append((
            float_atime,
            int_size,
            str_filename,
            dict_slide.get("str_rel_path") or "",
            tiles_dir,
        ))
        int_total += int_size

    if int_total <= int_quota:
        return

    list_entries.sort(key=lambda x: x[0])  # text text

    int_freed = 0
    int_evicted = 0
    for float_atime, int_size, str_filename, str_rel_path, tiles_dir in list_entries:
        if int_total - int_freed <= int_quota:
            break
        try:
            removed = await loop.run_in_executor(bg_executor, _remove_tiles, tiles_dir)
            if not removed:
                continue
        except Exception as e:
            print(f"[tile_janitor] rmtree failed {str_filename}: {e}")
            continue
        try:
            await slide_store.mark_tiles_ready(str_rel_path, str_filename, False)
        except Exception as e:
            print(f"[tile_janitor] DB flag reset failed {str_filename}: {e}")
        int_freed += int_size
        int_evicted += 1
        print(
            f"[tile_janitor] evicted {str_filename} "
            f"(size={int_size / 1024 / 1024:.1f}MB)"
        )

    print(
        f"[tile_janitor] total={int_total / 1024 / 1024 / 1024:.2f}GB "
        f"quota={int_quota / 1024 / 1024 / 1024:.2f}GB "
        f"freed={int_freed / 1024 / 1024 / 1024:.2f}GB "
        f"evicted={int_evicted}"
    )
