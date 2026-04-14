"""뷰어 타일 백그라운드 생성 워커.

정책:
- 시작 시 한 번, DB 의 모든 슬라이드에 대해 디스크 마커(.complete JSON) 의 ICC 해시가
  현재 슬라이드 상태와 일치하는지 검증한다. 불일치 시 tile dir 삭제 + DB 플래그 리셋.
  (DB/환경 이주 시 stale 캐시가 영구 고착되는 것을 방지)
- 이후 주기적으로 DB 를 스캔해 `bool_tiles_ready=False` 인 슬라이드를 찾는다.
- 사용자 활동 유무와 무관하게 계속 돌려 최우선으로 타일을 만든다.
- 한 번에 한 슬라이드씩 순차 처리 (디스크/CPU 쓰래싱 방지).
- auto_ai 워커는 별도로 `has_any_pending_tiles()` 를 체크해 타일이 미완료면 추론을 보류.

Claude.md 규칙 준수 (str_/int_/bool_/list_/dict_ 접두어).
"""

import asyncio
from pathlib import Path
from typing import Optional

# 백그라운드 타일 생성용 executor — cpu_layout 에서 핀닝된 풀 재사용.
# (이전엔 모듈 로컬 ThreadPoolExecutor 였지만 cores 분배를 일관되게 하기 위해 통합)
from app.cpu_layout import bg_executor as _bg_executor


SCAN_INTERVAL_SECONDS = 20
# janitor 실행 주기 — 스캔 카운트 기준. 20s * 15 = 5분마다 한 번.
JANITOR_EVERY_N_SCANS = 15

_worker_task: Optional[asyncio.Task] = None
_int_scan_count = 0


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

    # 2) 디스크 마커가 현재 슬라이드의 ICC 상태와 일치하면 DB 만 동기화
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

    # 3) 마커가 없거나 stale → 기존 tile dir 를 지우고 재생성
    #    (기존 tile 파일이 남아 있으면 _generate_tiles 가 존재 파일은 스킵하므로
    #     반드시 선삭제해야 새 ICC 설정으로 완전 재생성된다.)
    tile_generator.invalidate_tiles(str_filename)
    print(f"[tile_worker] generating tiles: {str_filename}")
    await loop.run_in_executor(
        _bg_executor, tile_generator._generate_tiles, str_filename, str_full_path
    )
    # 안전장치 — threadsafe 마킹이 메인 루프 타이밍 이슈로 못 올 수 있어 한 번 더
    await slide_store.mark_tiles_ready(str_rel_path, str_filename, True)
    print(f"[tile_worker] done: {str_filename}")
    return True


async def _startup_validate_all() -> None:
    """시작 시 1회: DB 의 모든 슬라이드에 대해 .complete 마커를 검증.

    `bool_tiles_ready=True` 인 슬라이드 중 마커가 stale/legacy/ICC 불일치인 것이
    있으면 tile dir 를 삭제하고 DB 플래그를 False 로 되돌려 일반 스캔 루프가
    다시 생성하도록 한다. DB 만 복사되고 tiles 만 남은 (또는 그 반대) 환경에서
    자동 복구를 보장.
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
        tile_generator.invalidate_tiles(str_filename)
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
