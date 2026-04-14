"""
타일 서빙 API — 프리제네레이트된 타일 반환, 없으면 즉석 생성 후 저장
유저가 보고 있는 영역의 타일이 최우선, 나머지는 백그라운드에서 채워짐
"""

import io
import asyncio
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app.auth import get_current_user
from app.config import settings
from app.slide_manager import slide_manager
from app.tile_generator import get_tiles_dir
from app.priority import notify_viewer_activity

router = APIRouter(dependencies=[Depends(get_current_user)])

TILE_SIZE = settings.TILE_SIZE


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
        tile = info.slide.read_region((x, y), level, (TILE_SIZE, TILE_SIZE))
        tile_rgb = info.apply_icc(tile.convert("RGB"))
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        tile_rgb.save(str(tile_path), "JPEG", quality=settings.TILE_QUALITY)
        buf = io.BytesIO()
        tile_rgb.save(buf, format="JPEG", quality=settings.TILE_QUALITY)
        return buf.getvalue()

    try:
        # 블로킹 디코딩/인코딩은 스레드로 — 이벤트 루프 차단 방지
        content = await asyncio.to_thread(_render_and_save)
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
