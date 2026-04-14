"""타일 디스크 캐시 janitor — LRU + 쿼터 기반 eviction.

정책:
- settings.TILE_CACHE_QUOTA_BYTES 를 초과하면 오래된 슬라이드 타일 디렉토리를 삭제.
- "오래됨" 기준: `.complete` 마커 파일의 mtime (tiles.py 가 서빙 시 throttled touch).
  마커 없으면 디렉토리 mtime fallback.
- 현재 slide_manager 에 열려 있는 (활성 뷰잉) 슬라이드는 보호 — stem 이 동일한 경우 skip.
- 삭제 후 DB `bool_tiles_ready` 를 False 로 되돌려 tile_worker 가 필요 시 재생성.
- 마커가 stale 판정된 tile dir (보통 tile_worker startup validation 이 처리) 도
  참여한다 — 이들은 어차피 재생성 대상이지만 쿼터 계산에는 포함시킨다.

Claude.md 규칙 준수 (str_/int_/bool_/list_/dict_/float_ 접두어).
"""

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


async def run_janitor_once() -> None:
    """쿼터 초과 시 LRU 기준 eviction 1회 실행."""
    from app.config import settings
    from app.database import is_db_connected, get_db
    from app import tile_generator, slide_store
    from app.slide_manager import slide_manager

    int_quota = settings.TILE_CACHE_QUOTA_BYTES
    if int_quota <= 0:
        return
    if not is_db_connected():
        return

    db = get_db()

    # 활성 슬라이드 stem 집합 — 현재 열려 있는 것은 보호
    set_active_stems = set()
    for str_sid, dict_info in slide_manager.list_slides().items():
        try:
            set_active_stems.add(Path(dict_info["file_path"]).stem)
        except Exception:
            continue

    list_entries: List[Tuple[float, int, str, str, Path]] = []
    int_total = 0

    cursor = db.slides.find(
        {"bool_tiles_ready": True},
        {"str_filename": 1, "str_rel_path": 1, "_id": 0},
    )
    async for dict_slide in cursor:
        str_filename = dict_slide.get("str_filename") or ""
        if not str_filename:
            continue
        tiles_dir = tile_generator.get_tiles_dir(str_filename)
        if not tiles_dir.exists():
            continue
        if Path(str_filename).stem in set_active_stems:
            continue
        int_size = _dir_size(tiles_dir)
        float_atime = _entry_atime(tiles_dir)
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

    list_entries.sort(key=lambda x: x[0])  # 오래된 순

    int_freed = 0
    int_evicted = 0
    for float_atime, int_size, str_filename, str_rel_path, tiles_dir in list_entries:
        if int_total - int_freed <= int_quota:
            break
        try:
            shutil.rmtree(tiles_dir, ignore_errors=True)
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
