"""
text text API — text text text, text text text text text
text text text text text text, text text text
"""

import io
import asyncio
import hashlib
import os
import threading
import time
from pathlib import Path

# text TILE_DEBUG=1 text _render_and_save text text wall-time text text
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
from app.tile_generator import (
    generate_priority_single_tile,
    get_tiles_dir,
    image_to_white_rgb,
    request_priority_tile,
)
from app.philips_proxy import is_philips_isyntax
from app.priority import notify_viewer_activity
from app.cpu_layout import viewer_executor
from app.thread_slide_pool import get_thread_slide

# text <img src> text text media-ticket(text ?mt=) text text
# get_media_user text text. text text stage-level text text API text Bearer JWT text.
router = APIRouter()

TILE_SIZE = TILE_SIZE_OUT
_BLANK_TILE_BYTES: bytes | None = None


def _blank_tile_bytes() -> bytes:
    global _BLANK_TILE_BYTES
    if _BLANK_TILE_BYTES is None:
        obj_img = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (255, 255, 255))
        buf = io.BytesIO()
        obj_img.save(buf, format="JPEG", quality=85)
        obj_img.close()
        _BLANK_TILE_BYTES = buf.getvalue()
    return _BLANK_TILE_BYTES


def _blank_tile_response(cache_control: str = "no-store") -> Response:
    return Response(
        content=_blank_tile_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": cache_control},
    )


def _rects_intersect(rect_a: tuple[int, int, int, int], rect_b: tuple[int, int, int, int]) -> bool:
    ax0, ax1, ay0, ay1 = rect_a
    bx0, bx1, by0, by1 = rect_b
    return ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1


def _tile_intersects_data_envelope(info, level: int, tile_x: int, tile_y: int) -> bool:
    rects = [
        tuple(int(v) for v in rect)
        for rect in getattr(info.slide, "data_envelope_rectangles", [])
        if len(rect) == 4
    ]
    if not rects:
        return True
    int_read_size = STAGE_READ_SIZE[level]
    x0 = tile_x * int_read_size
    y0 = tile_y * int_read_size
    tile_rect = (x0, x0 + int_read_size - 1, y0, y0 + int_read_size - 1)
    return any(_rects_intersect(tile_rect, rect) for rect in rects)


async def _ensure_philips_tile(info, filename: str, level: int, tile_x: int, tile_y: int, tile_path: Path) -> bool:
    if not _tile_intersects_data_envelope(info, level, tile_x, tile_y):
        return False
    request_priority_tile(filename, info.file_path, level, tile_x, tile_y)
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            viewer_executor,
            generate_priority_single_tile,
            filename,
            info.file_path,
            level,
            tile_x,
            tile_y,
        )
    except Exception as exc:
        print(f"[tiles] Philips priority tile failed ({filename} S{level} {tile_x},{tile_y}): {exc}")
        return False
    return tile_path.exists()


async def _missing_philips_tile_response(
    info,
    filename: str,
    level: int,
    tile_x: int,
    tile_y: int,
    tile_path: Path,
) -> Response:
    bool_intersects_data = _tile_intersects_data_envelope(info, level, tile_x, tile_y)
    if await _ensure_philips_tile(info, filename, level, tile_x, tile_y, tile_path):
        return FileResponse(
            tile_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )
    if bool_intersects_data:
        return _blank_tile_response("no-store")
    return _blank_tile_response("public, max-age=604800")


# ── LRU text text touch (janitor text) ──
# tile text text `.complete` text mtime text text tile_janitor text LRU text
# text. per-slide 60s throttle — utime text text.
_dict_access_touch: dict[str, float] = {}
_ACCESS_TOUCH_THROTTLE_SEC = 60.0


def _touch_slide_access(slide_id: str, tiles_root: Path) -> None:
    float_now = time.time()
    if len(_dict_access_touch) > 2048:
        float_cutoff = float_now - 24 * 60 * 60
        for str_key, float_ts in list(_dict_access_touch.items()):
            if float_ts < float_cutoff:
                _dict_access_touch.pop(str_key, None)
    if _dict_access_touch.get(slide_id, 0.0) + _ACCESS_TOUCH_THROTTLE_SEC > float_now:
        return
    _dict_access_touch[slide_id] = float_now
    try:
        marker = tiles_root / ".complete"
        if marker.exists():
            os.utime(marker, None)
    except Exception:
        pass


# ── Thread-local OpenSlide text text ──
# app.thread_slide_pool.get_thread_slide text text generation text + LRU eviction
# text text text text. SlideManager.close() text generation text bump text
# text text text text text text stale text text text (leak text).


def _find_and_open(slide_id: str):
    """slide_managertext text uploadstext text text text"""
    info = slide_manager.get(slide_id)
    if info:
        return info

    # uploads text text text md5 text
    upload_dir = Path(settings.UPLOAD_DIR)
    for f in upload_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
            if hashlib.md5(f.name.encode()).hexdigest()[:12] == slide_id:
                return slide_manager.open(slide_id, str(f))
    return None


# ── NDP text text text text ──
# /ndp/ text — stored raw text ndp_color_match.apply_ndp_fit text text
# tiles/<stem>/ndpmatch/<level>/<x>_<y>.jpeg text text text text text.
# Hamamatsu text "NDP text ON" text text URL text text.
@router.get("/{slide_id}/ndp/{level}/{tile_x}/{tile_y}.jpeg")
async def get_tile_ndp(
    slide_id: str,
    level: int,
    tile_x: int,
    tile_y: int,
    dict_user: dict = Depends(get_media_user),
):
    """NDP.view2 text text text text text.

    text: tiles/<stem>/ndpmatch/<level>/<x>_<y>.jpeg
      - text text text (disk → static)
      - text raw text (text text text text) text apply_ndp_fit text → text → text
    """
    from app.ndp_color_match import apply_ndp_fit

    notify_viewer_activity()

    info = _find_and_open(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")
    if level < 0 or level >= STAGE_COUNT:
        raise HTTPException(400, f"text stage: {level}")

    filename = Path(info.file_path).name
    tiles_root = get_tiles_dir(filename)
    _touch_slide_access(slide_id, tiles_root)

    path_ndp_tile = tiles_root / "ndpmatch" / str(level) / f"{tile_x}_{tile_y}.jpeg"
    if path_ndp_tile.exists():
        return FileResponse(
            path_ndp_tile,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    # raw text text (text text text text text)
    path_raw_tile = tiles_root / str(level) / f"{tile_x}_{tile_y}.jpeg"
    int_read_size = STAGE_READ_SIZE[level]
    if is_philips_isyntax(info.file_path) and not path_raw_tile.exists():
        if not await _ensure_philips_tile(info, filename, level, tile_x, tile_y, path_raw_tile):
            if _tile_intersects_data_envelope(info, level, tile_x, tile_y):
                return _blank_tile_response("no-store")
            return _blank_tile_response("public, max-age=604800")

    def _make_ndp_variant() -> bytes:
        # (1) raw text text
        if not path_raw_tile.exists():
            obj_slide = get_thread_slide(slide_id, info.file_path)
            obj_region = obj_slide.read_region(
                (tile_x * int_read_size, tile_y * int_read_size),
                0,
                (int_read_size, int_read_size),
            )
            obj_rgb = image_to_white_rgb(obj_region)
            obj_rgb = info.apply_icc(obj_rgb)
            if int_read_size != TILE_SIZE:
                obj_rgb = obj_rgb.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
            path_raw_tile.parent.mkdir(parents=True, exist_ok=True)
            obj_rgb.save(str(path_raw_tile), "JPEG", quality=settings.TILE_QUALITY)
            obj_region.close()
        else:
            with Image.open(str(path_raw_tile)) as obj_file:
                obj_rgb = obj_file.convert("RGB")

        # (2) NDP fit text → text
        obj_ndp = apply_ndp_fit(obj_rgb)
        path_ndp_tile.parent.mkdir(parents=True, exist_ok=True)
        obj_ndp.save(str(path_ndp_tile), "JPEG", quality=settings.TILE_QUALITY)

        # (3) text text
        buf = io.BytesIO()
        obj_ndp.save(buf, format="JPEG", quality=settings.TILE_QUALITY)
        try:
            obj_rgb.close()
        except Exception:
            pass
        try:
            obj_ndp.close()
        except Exception:
            pass
        return buf.getvalue()

    try:
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(viewer_executor, _make_ndp_variant)
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )
    except Exception as e:
        raise HTTPException(500, f"NDP text text text text: {e}")


@router.get("/{slide_id}/{level}/{tile_x}/{tile_y}.jpeg")
async def get_tile(
    slide_id: str,
    level: int,
    tile_x: int,
    tile_y: int,
    dict_user: dict = Depends(get_media_user),
):
    """
    text text: text text text text, text text text + text.

    `level` text 3text stage index (0, 1, 2) — OpenSlide level text text.
    text text level 0 text text STAGE_DOWNSAMPLES[stage] text text.
    """
    # text text text — AI text text text text
    notify_viewer_activity()

    info = _find_and_open(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")

    filename = Path(info.file_path).name
    tiles_root = get_tiles_dir(filename)
    tile_path = tiles_root / str(level) / f"{tile_x}_{tile_y}.jpeg"
    _touch_slide_access(slide_id, tiles_root)

    # 1) text text text text text
    if tile_path.exists():
        return FileResponse(
            tile_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    # 2) text text text → text text → text
    if level < 0 or level >= STAGE_COUNT:
        raise HTTPException(400, f"text stage: {level}")

    int_read_size = STAGE_READ_SIZE[level]  # 1024 / 4096 / 8192
    int_sx = tile_x * int_read_size
    int_sy = tile_y * int_read_size
    if is_philips_isyntax(info.file_path):
        return await _missing_philips_tile_response(info, filename, level, tile_x, tile_y, tile_path)

    def _render_and_save() -> bytes:
        # thread-local text read — text text text text text text text
        obj_slide = get_thread_slide(slide_id, info.file_path)
        float_t0 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        obj_region = obj_slide.read_region(
            (int_sx, int_sy), 0, (int_read_size, int_read_size)
        )
        float_t1 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        obj_rgb = image_to_white_rgb(obj_region)
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
        try:
            obj_rgb.close()
        except Exception:
            pass
        return buf.getvalue()

    try:
        # viewer text pool — viewer cores text text (cpu_layout)
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(viewer_executor, _render_and_save)
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )
    except Exception as e:
        raise HTTPException(500, f"text text text: {e}")


@router.get("/{slide_id}/stage-level")
async def get_stage_level(
    slide_id: str,
    effective_mpp: float = Query(..., description="text text effective MPP"),
    dict_user: dict = Depends(get_current_user),
):
    """effective MPP text stage index (0/1/2) text."""
    info = _find_and_open(slide_id)
    if not info:
        raise HTTPException(404, "text text text text")

    int_stage = info.get_stage(effective_mpp)
    return {
        "level": int_stage,
        "stage": int_stage,
        "stage_dimensions": info.stage_dimensions[int_stage],
        "downsample": info.stage_downsamples[int_stage],
    }
