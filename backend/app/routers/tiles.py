"""
타일 서빙 API — 프리제네레이트된 타일 반환, 없으면 즉석 생성 후 저장
유저가 보고 있는 영역의 타일이 최우선, 나머지는 백그라운드에서 채워짐
"""

import io
import asyncio
import hashlib
import os
import threading
import time
from pathlib import Path

# 환경변수 TILE_DEBUG=1 이면 _render_and_save 의 단계별 wall-time 을 출력
_BOOL_TILE_DEBUG = os.environ.get("TILE_DEBUG", "").lower() in ("1", "true", "yes")

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from PIL import Image

from app.auth import get_current_user, get_media_user
from app.config import settings
from app.slide_manager import (
    slide_manager,
    STAGE_READ_SIZE,
    STAGE_COUNT,
    TILE_SIZE_OUT,
)
from app.tile_generator import get_tiles_dir
from app.priority import notify_viewer_activity
from app.cpu_layout import viewer_executor
from app.thread_slide_pool import get_thread_slide

# 타일은 <img src> 로 로드되므로 media-ticket(쿼리 ?mt=) 도 허용하는
# get_media_user 를 쓴다. 그 외 stage-level 같은 일반 API 는 Bearer JWT 만.
router = APIRouter()

TILE_SIZE = TILE_SIZE_OUT


# ── LRU 접근 시각 touch (janitor 용) ──
# tile 서빙 시 `.complete` 마커의 mtime 을 갱신해 tile_janitor 가 LRU 판단에
# 사용한다. per-slide 60s throttle — utime 호출을 최소화.
_dict_access_touch: dict[str, float] = {}
_ACCESS_TOUCH_THROTTLE_SEC = 60.0


def _touch_slide_access(slide_id: str, tiles_root: Path) -> None:
    float_now = time.time()
    if _dict_access_touch.get(slide_id, 0.0) + _ACCESS_TOUCH_THROTTLE_SEC > float_now:
        return
    _dict_access_touch[slide_id] = float_now
    try:
        marker = tiles_root / ".complete"
        if marker.exists():
            os.utime(marker, None)
    except Exception:
        pass


# ── Thread-local OpenSlide 핸들 풀 ──
# app.thread_slide_pool.get_thread_slide 을 통해 generation 검증 + LRU eviction
# 이 적용된 핸들을 얻는다. SlideManager.close() 시 generation 이 bump 되어
# 모든 워커가 다음 접근 시 자기 stale 핸들을 자동으로 닫는다 (leak 방지).


def _find_and_open(slide_id: str):
    """slide_manager에 없으면 uploads에서 찾아 자동으로 열기"""
    info = slide_manager.get(slide_id)
    if info:
        return info

    # uploads 디렉토리 재귀 탐색으로 md5 매칭
    upload_dir = Path(settings.UPLOAD_DIR)
    for f in upload_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
            if hashlib.md5(f.name.encode()).hexdigest()[:12] == slide_id:
                return slide_manager.open(slide_id, str(f))
    return None


@router.get("/{slide_id}/{level}/{tile_x}/{tile_y}.jpeg")
async def get_tile(
    slide_id: str,
    level: int,
    tile_x: int,
    tile_y: int,
    dict_user: dict = Depends(get_media_user),
):
    """
    타일 반환: 디스크에 있으면 정적 서빙, 없으면 즉석 생성 + 저장.

    `level` 파라미터는 3단계 stage index (0, 1, 2) — OpenSlide level 과 무관.
    타일은 모두 level 0 에서 읽어 STAGE_DOWNSAMPLES[stage] 만큼 리사이즈.
    """
    # 뷰어 활동 신호 — AI 워커가 이 동안 양보한다
    notify_viewer_activity()

    info = _find_and_open(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    filename = Path(info.file_path).name
    tiles_root = get_tiles_dir(filename)
    tile_path = tiles_root / str(level) / f"{tile_x}_{tile_y}.jpeg"
    _touch_slide_access(slide_id, tiles_root)

    # 1) 프리제네레이트된 타일이 있으면 바로 반환
    if tile_path.exists():
        return FileResponse(
            tile_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    # 2) 없으면 즉석 생성 → 디스크 저장 → 반환
    if level < 0 or level >= STAGE_COUNT:
        raise HTTPException(400, f"잘못된 stage: {level}")

    int_read_size = STAGE_READ_SIZE[level]  # 1024 / 4096 / 8192
    int_sx = tile_x * int_read_size
    int_sy = tile_y * int_read_size

    def _render_and_save() -> bytes:
        # thread-local 핸들로 read — 같은 슬라이드를 여러 코어에서 병렬 디코딩 가능
        obj_slide = get_thread_slide(slide_id, info.file_path)
        float_t0 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        obj_region = obj_slide.read_region(
            (int_sx, int_sy), 0, (int_read_size, int_read_size)
        )
        float_t1 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        obj_rgb = obj_region.convert("RGB")
        obj_rgb = info.apply_icc(obj_rgb)
        if int_read_size != TILE_SIZE:
            obj_rgb = obj_rgb.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
        float_t2 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        tile_path.parent.mkdir(parents=True, exist_ok=True)
        obj_rgb.save(str(tile_path), "JPEG", quality=settings.TILE_QUALITY)
        float_t3 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        buf = io.BytesIO()
        obj_rgb.save(buf, format="JPEG", quality=settings.TILE_QUALITY)
        float_t4 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        if _BOOL_TILE_DEBUG:
            print(
                f"[tiles] {threading.current_thread().name} S{level} "
                f"read={int((float_t1-float_t0)*1000)}ms "
                f"rgb+resize={int((float_t2-float_t1)*1000)}ms "
                f"savedisk={int((float_t3-float_t2)*1000)}ms "
                f"encode={int((float_t4-float_t3)*1000)}ms "
                f"total={int((float_t4-float_t0)*1000)}ms"
            )
        obj_region.close()
        return buf.getvalue()

    try:
        # viewer 전용 pool — viewer cores 에 핀닝됨 (cpu_layout)
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(viewer_executor, _render_and_save)
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )
    except Exception as e:
        raise HTTPException(500, f"타일 생성 실패: {e}")


@router.get("/{slide_id}/stage-level")
async def get_stage_level(
    slide_id: str,
    effective_mpp: float = Query(..., description="현재 화면의 effective MPP"),
    dict_user: dict = Depends(get_current_user),
):
    """effective MPP 기반 stage index (0/1/2) 반환."""
    info = _find_and_open(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    int_stage = info.get_stage(effective_mpp)
    return {
        "level": int_stage,
        "stage": int_stage,
        "stage_dimensions": info.stage_dimensions[int_stage],
        "downsample": info.stage_downsamples[int_stage],
    }
