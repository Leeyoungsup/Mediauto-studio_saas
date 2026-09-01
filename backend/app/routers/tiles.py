"""
text text API — text text text, text text text text text
text text text text text text, text text text
"""

import io
import asyncio
import os
import threading
import time
from pathlib import Path

# text TILE_DEBUG=1 text _render_and_save text text wall-time text text
_BOOL_TILE_DEBUG = os.environ.get("TILE_DEBUG", "").lower() in ("1", "true", "yes")

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    blank_tile_marker_exists,
    invalidate_tiles,
    generate_priority_single_tile,
    get_tiles_dir_for_path,
    image_to_white_rgb,
    read_region_for_output,
    is_completed_cache_tile_repair_pending,
    queue_completed_cache_tile_repair,
    request_priority_tile,
    tiles_marker_matches_file,
)
from app.philips_proxy import is_philips_isyntax
from app.priority import notify_viewer_activity
from app.cpu_layout import INT_VIEWER, viewer_executor
from app.slide_identity import slide_cache_key
from app.thread_slide_pool import get_thread_slide

# text <img src> text text media-ticket(text ?mt=) text text
# get_media_user text text. text text stage-level text text API text Bearer JWT text.
router = APIRouter()

TILE_SIZE = TILE_SIZE_OUT
_BLANK_TILE_BYTES: bytes | None = None
_INLINE_ACTIVE = 0
_INLINE_ACTIVE_LOCK = threading.Lock()
_INLINE_MAX_ACTIVE = max(1, int(os.environ.get("MEDIAUTO_TILE_INLINE_MAX_ACTIVE", max(1, min(4, INT_VIEWER // 3)))))
_INLINE_QUEUE_LIMIT = max(1, int(os.environ.get("MEDIAUTO_TILE_INLINE_QUEUE_LIMIT", max(2, INT_VIEWER // 2))))
_INLINE_TIMEOUT_MS = {
    0: max(50, int(os.environ.get("MEDIAUTO_TILE_INLINE_TIMEOUT_L0_MS", "1400"))),
    1: max(50, int(os.environ.get("MEDIAUTO_TILE_INLINE_TIMEOUT_L1_MS", "1000"))),
    2: max(50, int(os.environ.get("MEDIAUTO_TILE_INLINE_TIMEOUT_L2_MS", "700"))),
}
_INLINE_PHILIPS_TIMEOUT_MS = max(50, int(os.environ.get("MEDIAUTO_TILE_INLINE_PHILIPS_TIMEOUT_MS", "650")))
_INLINE_DICOM_TIMEOUT_MS = max(1000, int(os.environ.get("MEDIAUTO_TILE_INLINE_DICOM_TIMEOUT_MS", "8000")))


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


def _jpeg_file_response(path: Path, cache_control: str = "public, max-age=604800") -> FileResponse:
    """Serve a cached tile without synchronously reading it on the event loop.

    The previous ``path.read_bytes()`` implementation performed the complete
    disk read before returning a response.  During viewport loads several
    cache-hit tiles can arrive together, so slow storage could block the ASGI
    event loop and delay unrelated API/image requests.  FileResponse streams
    the file through Starlette's threadpool-backed file response path.
    """
    return FileResponse(
        path=str(path),
        media_type="image/jpeg",
        headers={"Cache-Control": cache_control},
    )


def _save_jpeg_atomic(obj_img: Image.Image, path: Path, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{threading.get_ident()}.{time.time_ns()}.tmp")
    try:
        obj_img.save(str(tmp_path), "JPEG", quality=quality)
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def _consume_future_exception(fut) -> None:
    try:
        fut.exception()
    except BaseException:
        pass


def _viewer_queue_size() -> int:
    queue_obj = getattr(viewer_executor, "_work_queue", None)
    if queue_obj is None:
        return 0
    try:
        return int(queue_obj.qsize())
    except Exception:
        return 0


def _inline_active_count() -> int:
    with _INLINE_ACTIVE_LOCK:
        return _INLINE_ACTIVE


def _tile_inline_timeout_seconds(level: int, bool_philips: bool) -> float:
    if bool_philips:
        return _INLINE_PHILIPS_TIMEOUT_MS / 1000.0
    return _INLINE_TIMEOUT_MS.get(level, _INLINE_TIMEOUT_MS[2]) / 1000.0


def _can_inline_generate(level: int, bool_philips: bool) -> bool:
    if _inline_active_count() >= _INLINE_MAX_ACTIVE:
        return False
    if _viewer_queue_size() >= _INLINE_QUEUE_LIMIT:
        return False
    # Whole-slide generators now yield between reads while the viewer is
    # active.  Refusing an inline tile merely because such a generator exists
    # would leave both sides waiting and cause repeated 503 retries.
    return True


def _pending_tile_response() -> Response:
    return Response(
        status_code=503,
        content=b"",
        media_type="text/plain",
        headers={
            "Cache-Control": "no-store",
            "Retry-After": "1",
            "X-Mediauto-Tile-State": "queued",
        },
    )


async def _run_viewer_job(request: Request, fn, *, timeout_seconds: float | None = None):
    loop = asyncio.get_running_loop()
    obj_cancel = threading.Event()

    def _tracked_fn():
        global _INLINE_ACTIVE
        with _INLINE_ACTIVE_LOCK:
            _INLINE_ACTIVE += 1
        try:
            return fn(obj_cancel)
        finally:
            with _INLINE_ACTIVE_LOCK:
                _INLINE_ACTIVE -= 1

    fut = loop.run_in_executor(viewer_executor, _tracked_fn)
    float_started = time.monotonic()
    while True:
        done, _ = await asyncio.wait({fut}, timeout=0.1)
        if done:
            return fut.result()
        if timeout_seconds is not None and time.monotonic() - float_started >= timeout_seconds:
            # This is only the HTTP response budget, not a client cancellation.
            # If the OpenSlide read is already running, let it finish and cache
            # the tile so the browser retry can use it.  Cancelling here made
            # every slow (> timeout) tile restart from zero and could leave the
            # viewer permanently blank.
            if not fut.cancel():
                fut.add_done_callback(_consume_future_exception)
            raise HTTPException(status_code=503, detail="Tile generation queued", headers={"Retry-After": "1"})
        if await request.is_disconnected():
            obj_cancel.set()
            if not fut.cancel():
                fut.add_done_callback(_consume_future_exception)
            raise HTTPException(status_code=499, detail="Client closed request")


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


async def _ensure_philips_tile(
    request: Request,
    info,
    filename: str,
    level: int,
    tile_x: int,
    tile_y: int,
    tile_path: Path,
    timeout_seconds: float | None = None,
) -> bool:
    if not _tile_intersects_data_envelope(info, level, tile_x, tile_y):
        return False
    request_priority_tile(filename, info.file_path, level, tile_x, tile_y)
    try:
        await _run_viewer_job(
            request,
            lambda obj_cancel: generate_priority_single_tile(
                filename,
                info.file_path,
                level,
                tile_x,
                tile_y,
                info.slide,
                info.apply_icc,
                cancel_event=obj_cancel,
            ),
            timeout_seconds=timeout_seconds,
        )
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[tiles] Philips priority tile failed ({filename} S{level} {tile_x},{tile_y}): {exc}")
        return False
    return tile_path.exists()


async def _missing_philips_tile_response(
    request: Request,
    info,
    filename: str,
    level: int,
    tile_x: int,
    tile_y: int,
    tile_path: Path,
) -> Response:
    bool_intersects_data = _tile_intersects_data_envelope(info, level, tile_x, tile_y)
    if not bool_intersects_data:
        return _blank_tile_response("public, max-age=604800")

    if is_completed_cache_tile_repair_pending(info.file_path, level, tile_x, tile_y):
        return _pending_tile_response()
    request_priority_tile(filename, info.file_path, level, tile_x, tile_y)
    if not _can_inline_generate(level, True):
        queue_completed_cache_tile_repair(
            filename, info.file_path, level, tile_x, tile_y
        )
        return _pending_tile_response()

    try:
        bool_ready = await _ensure_philips_tile(
            request,
            info,
            filename,
            level,
            tile_x,
            tile_y,
            tile_path,
            timeout_seconds=_tile_inline_timeout_seconds(level, True),
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            return _pending_tile_response()
        raise
    if bool_ready:
        return _jpeg_file_response(tile_path)
    return _pending_tile_response()


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

    # Reopen from uploads using the same cache identity used for disk storage.
    upload_dir = Path(settings.UPLOAD_DIR)
    for f in upload_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
            if slide_cache_key(str(f)) == slide_id:
                return slide_manager.open(slide_id, str(f))
    return None


# ── NDP text text text text ──
# /ndp/ text — stored raw text ndp_color_match.apply_ndp_fit text text
# tiles/<stem>/ndpmatch/<level>/<x>_<y>.jpeg text text text text text.
# Hamamatsu text "NDP text ON" text text URL text text.
@router.get("/{slide_id}/ndp/{level}/{tile_x}/{tile_y}.jpeg")
async def get_tile_ndp(
    request: Request,
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
    tiles_root = get_tiles_dir_for_path(info.file_path)
    _touch_slide_access(slide_id, tiles_root)
    bool_cache_valid = tiles_marker_matches_file(filename, info.file_path)
    if not bool_cache_valid and (tiles_root / ".complete").exists():
        invalidate_tiles(filename, info.file_path)

    path_ndp_tile = tiles_root / "ndpmatch" / str(level) / f"{tile_x}_{tile_y}.jpeg"
    if bool_cache_valid and path_ndp_tile.exists():
        return _jpeg_file_response(path_ndp_tile)

    # raw text text (text text text text text)
    path_raw_tile = tiles_root / str(level) / f"{tile_x}_{tile_y}.jpeg"
    int_read_size = STAGE_READ_SIZE[level]
    if is_philips_isyntax(info.file_path) and not path_raw_tile.exists():
        if not await _ensure_philips_tile(request, info, filename, level, tile_x, tile_y, path_raw_tile):
            if _tile_intersects_data_envelope(info, level, tile_x, tile_y):
                return _blank_tile_response("no-store")
            return _blank_tile_response("public, max-age=604800")

    def _make_ndp_variant(obj_cancel: threading.Event) -> bytes:
        def _check_cancelled() -> None:
            if obj_cancel.is_set():
                raise RuntimeError("Tile request cancelled")

        obj_rgb = None
        obj_ndp = None
        try:
            # (1) raw text text
            _check_cancelled()
            if not path_raw_tile.exists():
                obj_slide = get_thread_slide(slide_id, info.file_path)
                obj_region = obj_slide.read_region(
                    (tile_x * int_read_size, tile_y * int_read_size),
                    0,
                    (int_read_size, int_read_size),
                )
                try:
                    _check_cancelled()
                    obj_rgb = image_to_white_rgb(obj_region)
                    _check_cancelled()
                    obj_rgb = info.apply_icc(obj_rgb)
                    if int_read_size != TILE_SIZE:
                        obj_rgb = obj_rgb.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
                    _check_cancelled()
                    _save_jpeg_atomic(obj_rgb, path_raw_tile, settings.TILE_QUALITY)
                finally:
                    obj_region.close()
            else:
                with Image.open(str(path_raw_tile)) as obj_file:
                    obj_rgb = obj_file.convert("RGB")

            # (2) NDP fit text → text
            _check_cancelled()
            obj_ndp = apply_ndp_fit(obj_rgb)
            _check_cancelled()
            _save_jpeg_atomic(obj_ndp, path_ndp_tile, settings.TILE_QUALITY)

            # (3) text text
            _check_cancelled()
            buf = io.BytesIO()
            obj_ndp.save(buf, format="JPEG", quality=settings.TILE_QUALITY)
            return buf.getvalue()
        finally:
            try:
                if obj_rgb is not None:
                    obj_rgb.close()
            except Exception:
                pass
            try:
                if obj_ndp is not None:
                    obj_ndp.close()
            except Exception:
                pass

    try:
        content = await _run_viewer_job(request, _make_ndp_variant)
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"NDP text text text text: {e}")


@router.get("/{slide_id}/{level}/{tile_x}/{tile_y}.jpeg")
async def get_tile(
    request: Request,
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
    tiles_root = get_tiles_dir_for_path(info.file_path)
    tile_path = tiles_root / str(level) / f"{tile_x}_{tile_y}.jpeg"
    _touch_slide_access(slide_id, tiles_root)
    path_complete_marker = tiles_root / ".complete"
    bool_cache_valid = tiles_marker_matches_file(filename, info.file_path)
    if not bool_cache_valid and path_complete_marker.exists():
        invalidate_tiles(filename, info.file_path)

    # A tile generated during the current background run is immediately usable.
    # Waiting for the whole-slide .complete marker caused the viewer to request
    # and decode the same DICOM frames repeatedly until the entire pyramid was
    # finished. A present but invalid marker was already purged above.
    if tile_path.exists() and (bool_cache_valid or not path_complete_marker.exists()):
        return _jpeg_file_response(tile_path)
    if blank_tile_marker_exists(tile_path) and (
        bool_cache_valid or not path_complete_marker.exists()
    ):
        return _blank_tile_response("public, max-age=604800")

    # 2) text text text → text text → text
    if level < 0 or level >= STAGE_COUNT:
        raise HTTPException(400, f"text stage: {level}")

    int_read_size = STAGE_READ_SIZE[level]  # 1024 / 4096 / 8192
    int_sx = tile_x * int_read_size
    int_sy = tile_y * int_read_size
    if is_philips_isyntax(info.file_path):
        return await _missing_philips_tile_response(request, info, filename, level, tile_x, tile_y, tile_path)

    if is_completed_cache_tile_repair_pending(info.file_path, level, tile_x, tile_y):
        return _pending_tile_response()
    request_priority_tile(filename, info.file_path, level, tile_x, tile_y)
    if not _can_inline_generate(level, False):
        queue_completed_cache_tile_repair(
            filename, info.file_path, level, tile_x, tile_y
        )
        return _pending_tile_response()

    def _render_and_save(obj_cancel: threading.Event) -> bytes:
        def _check_cancelled() -> None:
            if obj_cancel.is_set():
                raise RuntimeError("Tile request cancelled")

        # thread-local text read — text text text text text text text
        _check_cancelled()
        obj_slide = get_thread_slide(slide_id, info.file_path)
        float_t0 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0

        obj_region = None
        obj_rgb = None
        try:
            obj_region = read_region_for_output(
                obj_slide,
                (int_sx, int_sy),
                (int_read_size, int_read_size),
                (TILE_SIZE, TILE_SIZE),
            )
            float_t1 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0
            _check_cancelled()

            obj_rgb = image_to_white_rgb(obj_region)
            _check_cancelled()
            obj_rgb = info.apply_icc(obj_rgb)
            if obj_rgb.size != (TILE_SIZE, TILE_SIZE):
                obj_rgb = obj_rgb.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
            float_t2 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0
            _check_cancelled()

            _save_jpeg_atomic(obj_rgb, tile_path, settings.TILE_QUALITY)
            float_t3 = time.perf_counter() if _BOOL_TILE_DEBUG else 0.0
            _check_cancelled()

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
            return buf.getvalue()
        finally:
            if obj_region is not None:
                obj_region.close()
            try:
                if obj_rgb is not None:
                    obj_rgb.close()
            except Exception:
                pass

    try:
        # viewer text pool — viewer cores text text (cpu_layout)
        content = await _run_viewer_job(
            request,
            _render_and_save,
            timeout_seconds=max(
                _tile_inline_timeout_seconds(level, False),
                (_INLINE_DICOM_TIMEOUT_MS / 1000.0)
                if bool(getattr(info.slide, "is_dicom", False)) else 0.0,
            ),
        )
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )
    except HTTPException as exc:
        if exc.status_code == 503:
            return _pending_tile_response()
        raise
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
