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

from app.auth import get_current_user, get_media_user
from app.config import settings
from app.slide_manager import slide_manager
from app.tile_generator import get_tiles_dir
from app.priority import notify_viewer_activity
from app.cpu_layout import viewer_executor
from app.thread_slide_pool import get_thread_slide

# 타일은 <img src> 로 로드되므로 media-ticket(쿼리 ?mt=) 도 허용하는
# get_media_user 를 쓴다. 그 외 stage-level 같은 일반 API 는 Bearer JWT 만.
router = APIRouter()

TILE_SIZE = settings.TILE_SIZE


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
    """
    # 뷰어 활동 신호 — AI 워커가 이 동안 양보한다
    notify_viewer_activity()

    info = _find_and_open(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    filename = Path(info.file_path).name
    tile_path = get_tiles_dir(filename) / str(level) / f"{tile_x}_{tile_y}.jpeg"

    # 1) 프리제네레이트된 타일이 있으면 바로 반환
    if tile_path.exists():
        return FileResponse(
            tile_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    # 2) 없으면 즉석 생성 → 디스크 저장 → 반환
    if level < 0 or level >= info.level_count:
        raise HTTPException(400, f"잘못된 레벨: {level}")

    downsample = info.level_downsamples[level]
    x = int(tile_x * TILE_SIZE * downsample)
    y = int(tile_y * TILE_SIZE * downsample)

    def _render_and_save() -> bytes:
        # thread-local 핸들로 read — 같은 슬라이드를 여러 코어에서 병렬 디코딩 가능
        obj_slide = get_thread_slide(slide_id, info.file_path)
        if _BOOL_TILE_DEBUG:
            float_t0 = time.perf_counter()
            tile = obj_slide.read_region((x, y), level, (TILE_SIZE, TILE_SIZE))
            float_t1 = time.perf_counter()
            tile_rgb = tile.convert("RGB")
            float_t2 = time.perf_counter()
            tile_rgb = info.apply_icc(tile_rgb)
            float_t3 = time.perf_counter()
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            tile_rgb.save(str(tile_path), "JPEG", quality=settings.TILE_QUALITY)
            float_t4 = time.perf_counter()
            buf = io.BytesIO()
            tile_rgb.save(buf, format="JPEG", quality=settings.TILE_QUALITY)
            float_t5 = time.perf_counter()
            print(
                f"[tiles] {threading.current_thread().name} L{level} "
                f"read={int((float_t1-float_t0)*1000)}ms "
                f"rgb={int((float_t2-float_t1)*1000)}ms "
                f"icc={int((float_t3-float_t2)*1000)}ms "
                f"savedisk={int((float_t4-float_t3)*1000)}ms "
                f"encode={int((float_t5-float_t4)*1000)}ms "
                f"total={int((float_t5-float_t0)*1000)}ms"
            )
            return buf.getvalue()
        else:
            tile = obj_slide.read_region((x, y), level, (TILE_SIZE, TILE_SIZE))
            tile_rgb = info.apply_icc(tile.convert("RGB"))
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            tile_rgb.save(str(tile_path), "JPEG", quality=settings.TILE_QUALITY)
            buf = io.BytesIO()
            tile_rgb.save(buf, format="JPEG", quality=settings.TILE_QUALITY)
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
    """effective MPP 기반 4단계 레벨 반환"""
    info = _find_and_open(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    level = info.get_stage_level(effective_mpp)
    return {
        "level": level,
        "level_dimensions": info.level_dimensions[level],
        "downsample": info.level_downsamples[level],
    }
