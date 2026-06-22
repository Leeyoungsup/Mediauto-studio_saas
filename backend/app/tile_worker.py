"""text text text text text.

text:
- text text text text, DB text text text text text text(.complete JSON) text ICC text
  text text text text text. text text tile dir text + DB text text.
  (DB/text text text stale text text text text text)
- text text DB text text `bool_tiles_ready=False` text text text.
- text text text text text text text text text.
- text text text text text text (text/CPU text text).
- auto_ai text text `has_any_pending_tiles()` text text text text text text.

Claude.md text text (str_/int_/bool_/list_/dict_ text).
"""

import asyncio
from pathlib import Path
from typing import Optional

# text text text executor — cpu_layout text text text text.
# (text text text ThreadPoolExecutor text cores text text text text text)
from app.cpu_layout import bg_executor as _bg_executor


SCAN_INTERVAL_SECONDS = 20
# janitor text text — text text text. 20s * 15 = 5text text text.
JANITOR_EVERY_N_SCANS = 15

_worker_task: Optional[asyncio.Task] = None
_int_scan_count = 0


async def _process_one_slide(dict_slide: dict) -> bool:
    """text text text — text(True) text True, skip text text False."""
    from app import tile_generator, slide_store

    str_full_path = dict_slide.get("str_full_path") or ""
    str_filename = dict_slide.get("str_filename") or ""
    str_rel_path = dict_slide.get("str_rel_path") or ""

    # 1) text text → DB text True text text text text text
    if not str_full_path or not Path(str_full_path).exists():
        print(f"[tile_worker] file missing, marking ready: {str_filename} ({str_full_path})")
        await slide_store.mark_tiles_ready(str_rel_path, str_filename, True)
        return True

    # 2) text text text text ICC text text DB text text
    loop = asyncio.get_running_loop()
    try:
        bool_valid = await loop.run_in_executor(
            _bg_executor, tile_generator.tiles_are_valid, str_filename, str_full_path
        )
    except Exception as e:
        print(f"[tile_worker] tiles_are_valid error {str_filename}: {e}")
        bool_valid = False

    if bool_valid:
        print(f"[tile_worker] marker valid, syncing DB: {str_filename}")
        await slide_store.mark_tiles_ready(str_rel_path, str_filename, True)
        return True

    # 3) text text stale → text tile dir text text text
    #    (text tile text text text _generate_tiles text text text text
    #     text text text ICC text text text.)
    tile_generator.invalidate_tiles(str_filename, str_full_path)
    print(f"[tile_worker] generating tiles: {str_filename}")
    await loop.run_in_executor(
        _bg_executor, tile_generator._generate_tiles, str_filename, str_full_path
    )
    # text — threadsafe text text text text text text text text text text text text
    await slide_store.mark_tiles_ready(str_rel_path, str_filename, True)
    print(f"[tile_worker] done: {str_filename}")
    return True


async def _startup_validate_all() -> None:
    """text text 1text: DB text text text text .complete text text.

    `bool_tiles_ready=True` text text text text stale/legacy/ICC text text
    text tile dir text text DB text False text text text text text
    text text text. DB text text tiles text text (text text text) text
    text text text.
    """
    from app.database import is_db_connected, get_db
    from app import tile_generator, slide_store

    if not is_db_connected():
        return
    db = get_db()

    int_checked = 0
    int_reset = 0
    loop = asyncio.get_running_loop()
    cursor = db.slides.find(
        {"bool_tiles_ready": True},
        {
            "str_filename": 1,
            "str_full_path": 1,
            "str_rel_path": 1,
            "_id": 0,
        },
    )
    async for dict_slide in cursor:
        int_checked += 1
        str_filename = dict_slide.get("str_filename") or ""
        str_full_path = dict_slide.get("str_full_path") or ""
        str_rel_path = dict_slide.get("str_rel_path") or ""
        if not str_filename or not str_full_path or not Path(str_full_path).exists():
            continue
        try:
            bool_valid = await loop.run_in_executor(
                _bg_executor, tile_generator.tiles_are_valid, str_filename, str_full_path
            )
        except Exception as e:
            print(f"[tile_worker] validate error {str_filename}: {e}")
            continue
        if bool_valid:
            continue
        tile_generator.invalidate_tiles(str_filename, str_full_path)
        await slide_store.mark_tiles_ready(str_rel_path, str_filename, False)
        int_reset += 1
        print(f"[tile_worker] stale marker → queued for regen: {str_filename}")

    if int_checked:
        print(f"[tile_worker] startup validation: checked={int_checked} reset={int_reset}")


async def _scan_once() -> None:
    from app.database import is_db_connected
    from app import slide_store

    if not is_db_connected():
        return

    list_pending = await slide_store.list_slides_missing_tiles()
    if not list_pending:
        return

    print(f"[tile_worker] {len(list_pending)} slide(s) pending tile generation")
    for dict_slide in list_pending:
        try:
            await _process_one_slide(dict_slide)
        except Exception as e:
            import traceback
            print(f"[tile_worker] slide error: {e}\n{traceback.format_exc()}")


async def _worker_loop() -> None:
    print(f"[tile_worker] loop started (scan every {SCAN_INTERVAL_SECONDS}s)")
    try:
        await _startup_validate_all()
    except Exception as e:
        import traceback
        print(f"[tile_worker] startup validation error: {e}\n{traceback.format_exc()}")
    global _int_scan_count
    while True:
        try:
            await _scan_once()
            _int_scan_count += 1
            if _int_scan_count % JANITOR_EVERY_N_SCANS == 0:
                from app import tile_janitor
                await tile_janitor.run_janitor_once()
        except asyncio.CancelledError:
            print("[tile_worker] cancelled")
            raise
        except Exception as e:
            import traceback
            print(f"[tile_worker] loop error: {e}\n{traceback.format_exc()}")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def start_tile_worker() -> None:
    global _worker_task
    if _worker_task is not None:
        return
    _worker_task = asyncio.create_task(_worker_loop())


async def stop_tile_worker() -> None:
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
    print("[tile_worker] stopped")


def is_tile_worker_running() -> bool:
    return _worker_task is not None and not _worker_task.done()
