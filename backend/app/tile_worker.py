"""뷰어 타일 백그라운드 생성 워커.

정책:
- 주기적으로 DB 를 스캔해 `bool_tiles_ready=False` 인 슬라이드를 찾는다.
- 사용자 활동 유무와 무관하게 계속 돌려 최우선으로 타일을 만든다.
- 한 번에 한 슬라이드씩 순차 처리 (디스크/CPU 쓰래싱 방지).
- auto_ai 워커는 별도로 `has_any_pending_tiles()` 를 체크해 타일이 미완료면 추론을 보류.

Claude.md 규칙 준수 (str_/int_/bool_/list_/dict_ 접두어).
"""

import asyncio
from pathlib import Path
from typing import Optional


SCAN_INTERVAL_SECONDS = 20

_worker_task: Optional[asyncio.Task] = None


async def _process_one_slide(dict_slide: dict) -> bool:
    """한 슬라이드 처리 — 진행(True) 되었으면 True, skip 된 경우 False."""
    from app import tile_generator, slide_store

    str_full_path = dict_slide.get("str_full_path") or ""
    str_filename = dict_slide.get("str_filename") or ""
    str_rel_path = dict_slide.get("str_rel_path") or ""

    # 1) 파일 누락 → DB 플래그를 True 로 닫아 무한 재시도 방지
    if not str_full_path or not Path(str_full_path).exists():
        print(f"[tile_worker] file missing, marking ready: {str_filename} ({str_full_path})")
        await slide_store.mark_tiles_ready(str_rel_path, str_filename, True)
        return True

    # 2) 이미 디스크에 완료 마커가 있으면 DB 만 동기화
    if tile_generator.tiles_ready(str_filename):
        print(f"[tile_worker] .complete exists, syncing DB: {str_filename}")
        await slide_store.mark_tiles_ready(str_rel_path, str_filename, True)
        return True

    # 3) 실제 생성
    loop = asyncio.get_running_loop()
    print(f"[tile_worker] generating tiles: {str_filename}")
    await loop.run_in_executor(
        None, tile_generator._generate_tiles, str_filename, str_full_path
    )
    # 안전장치 — threadsafe 마킹이 메인 루프 타이밍 이슈로 못 올 수 있어 한 번 더
    await slide_store.mark_tiles_ready(str_rel_path, str_filename, True)
    print(f"[tile_worker] done: {str_filename}")
    return True


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
    while True:
        try:
            await _scan_once()
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
